#import "Bluetooth.h"
#import <objc/runtime.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

static NSString *const peer = @"00-11-22-33-44-55";
static NSString *const otherPeer = @"00-11-22-33-44-66";
static NSString *const spp = @"2e73a4ad-332d-41fc-90e2-16bef06523f2";
static NSString *const smep = @"f8620674-a1ed-41ab-a8b9-de9ad655729d";

static void check(bool passed, const char *reason) {
    if (!passed) {
        std::fprintf(stderr, "%s\n", reason);
        std::exit(1);
    }
}

// These fixtures implement the small IOBluetooth surface used by Bluetooth.mm.
// Unexpected framework calls on a fixture fail the test.
@interface SimRecord : NSObject
@property(nonatomic, strong) IOBluetoothSDPUUID *uuid;
@property(nonatomic, strong) IOBluetoothSDPUUID *classOverride;
@property(nonatomic) UInt8 channelID;
@property(nonatomic) BOOL classMissing;
@property(nonatomic) BluetoothSDPServiceRecordHandle serviceHandle;
@end
@implementation SimRecord
- (NSString *)getServiceName { return @"fixture"; }
- (id)getAttributeDataElement:(UInt16)attribute {
    return attribute == kBluetoothSDPAttributeIdentifierServiceClassIDList && !self.classMissing ? self : nil;
}
- (NSArray *)getArrayValue { return @[self]; }
- (IOBluetoothSDPUUID *)getUUIDValue { return self.classOverride ?: self.uuid; }
- (BOOL)matchesUUIDArray:(NSArray<IOBluetoothSDPUUID *> *)uuids {
    return uuids.count == 1 && [self.uuid isEqualToUUID:uuids.firstObject];
}
- (IOReturn)getServiceRecordHandle:(BluetoothSDPServiceRecordHandle *)value {
    *value = self.serviceHandle;
    return self.serviceHandle ? kIOReturnSuccess : kIOReturnError;
}
- (IOReturn)getRFCOMMChannelID:(UInt8 *)value {
    *value = self.channelID;
    return kIOReturnSuccess;
}
@end

@interface SimChannel : NSObject
@property(nonatomic, weak) id device;
@property(nonatomic, weak) id delegate;
@property(nonatomic) UInt8 channelID;
@property(nonatomic) BOOL open;
@property(nonatomic) BOOL failWrite;
@property(nonatomic) BOOL closeDuringWrite;
@property(nonatomic) NSUInteger closes;
@property(nonatomic, strong) NSMutableArray<NSData *> *writes;
@end
@implementation SimChannel
- (id)getDevice { return self.device; }
- (id)getDelegate { return self.delegate; }
- (UInt8)getChannelID { return self.channelID; }
- (BOOL)isIncoming { return NO; }
- (BluetoothRFCOMMMTU)getMTU { return 127; }
- (BOOL)isOpen { return self.open; }
- (IOReturn)closeChannel { ++_closes; self.open = NO; return kIOReturnSuccess; }
- (IOReturn)writeSync:(void *)bytes length:(UInt16)length {
    [self.writes addObject:[NSData dataWithBytes:bytes length:length]];
    if (self.closeDuringWrite) {
        self.open = NO;
        [self.delegate rfcommChannelClosed:(IOBluetoothRFCOMMChannel *)self];
    }
    return self.failWrite ? kIOReturnError : kIOReturnSuccess;
}
@end

@interface SimDevice : NSObject
@property(nonatomic) BOOL paired;
@property(nonatomic) BOOL fresh;
@property(nonatomic) BOOL baseband;
@property(nonatomic, strong) NSDate *servicesDate;
@property(nonatomic, strong) NSArray<SimRecord *> *services;
@property(nonatomic, strong) NSMutableArray<SimChannel *> *opened;
@end
@implementation SimDevice
- (BOOL)isConnected { return self.baseband; }
- (IOReturn)openConnection {
    check(false, "management forced a baseband connect while the SMEP channel reported open");
    return kIOReturnError;
}
- (BOOL)isPaired { return self.paired; }
- (NSString *)addressString { return peer; }
- (NSDate *)getLastServicesUpdate { return self.servicesDate; }
- (IOReturn)performSDPQuery:(id)delegate {
    if (self.fresh)
        self.servicesDate = [NSDate date];
    [delegate sdpQueryComplete:(IOBluetoothDevice *)self status:kIOReturnSuccess];
    return kIOReturnSuccess;
}
- (id)getServiceRecordForUUID:(IOBluetoothSDPUUID *)requested {
    for (SimRecord *record in self.services) {
        if (std::memcmp([requested getUUIDWithLength:16].bytes, record.uuid.bytes, 16) == 0)
            return record;
    }
    return nil;
}
- (IOReturn)openRFCOMMChannelSync:(IOBluetoothRFCOMMChannel **)result
                    withChannelID:(UInt8)channelID delegate:(id)delegate {
    SimChannel *channel = [SimChannel new];
    channel.device = self;
    channel.delegate = delegate;
    channel.channelID = channelID;
    channel.open = YES;
    channel.writes = [NSMutableArray array];
    [self.opened addObject:channel];
    if (delegate != nil && ![delegate isKindOfClass:[Bluetooth class]])
        CFRetain((__bridge CFTypeRef)channel); // IOBluetooth's secondary open returns a caller-owned reference.
    *result = (IOBluetoothRFCOMMChannel *)channel;
    return kIOReturnSuccess;
}
@end

static SimDevice *fixture;
static NSArray *pairedDevices(id, SEL) { return @[fixture]; }
static id lookupDevice(id, SEL, NSString *address) {
    check([address isEqualToString:peer], "unexpected device lookup");
    return fixture;
}
static void diagnostic(const char *) {}
static SimRecord *record(NSString *service, UInt8 channel) {
    uuid_t bytes;
    [[[NSUUID alloc] initWithUUIDString:service] getUUIDBytes:bytes];
    SimRecord *result = [SimRecord new];
    result.uuid = [IOBluetoothSDPUUID uuidWithBytes:bytes length:sizeof(bytes)];
    result.channelID = channel;
    return result;
}

// Each scenario starts at the public diagnostic connect entry point. No device
// lookup, SDP query, channel open or send is forwarded to a real device.
static Bluetooth *connect(NSArray<SimRecord *> *services, bool fresh = true, bool useDiagnostic = true) {
    fixture = [SimDevice new];
    fixture.paired = YES;
    fixture.fresh = fresh;
    fixture.baseband = YES;
    fixture.services = services;
    fixture.opened = [NSMutableArray array];
    uuid_t bytes;
    [[[NSUUID alloc] initWithUUIDString:spp] getUUIDBytes:bytes];
    Bluetooth *client = [Bluetooth new];
    check([client connect:peer uuid:bytes diagnostic:useDiagnostic ? diagnostic : nullptr] == BT_CONN_SUCCESS,
          "could not open simulated primary channel");
    return client;
}

static void exerciseTransport() {
    @autoreleasepool {
        Method lookup = class_getClassMethod([IOBluetoothDevice class], @selector(deviceWithAddressString:));
        check(lookup != nullptr, "device factory missing");
        method_setImplementation(lookup, (IMP)lookupDevice);
        Method paired = class_getClassMethod([IOBluetoothDevice class], @selector(pairedDevices));
        check(paired != nullptr, "paired devices lookup missing");
        method_setImplementation(paired, (IMP)pairedDevices);
        SimRecord *primary = record(spp, 4);
        SimRecord *secondary = record(smep, 7);
        NSArray *services = @[primary, secondary];

        uint64_t ticket = 0;
        Bluetooth *client = connect(@[primary]);
        check([client prepareBudsOnHandoff:peer ticket:&ticket] != 0 && fixture.opened.count == 1,
              "missing SMEP service opened a fallback channel");
        secondary.classMissing = YES;
        client = connect(services, false);
        check([client prepareBudsOnHandoff:peer ticket:&ticket] == 0 && fixture.opened.count == 2,
              "consistent cached UUID mapping should work without fresh SDP or a readable class");
        [client closeBudsOnHandoff:ticket];
        secondary.classMissing = NO;
        secondary.classOverride = primary.uuid;
        client = connect(services);
        check([client prepareBudsOnHandoff:peer ticket:&ticket] != 0 && fixture.opened.count == 1,
              "conflicting readable service class allowed preparation");
        secondary.classOverride = nil;
        client = connect(@[primary, secondary, record(@"00001101-0000-1000-8000-00805f9b34fb", 7)]);
        check([client prepareBudsOnHandoff:peer ticket:&ticket] != 0 && fixture.opened.count == 1,
              "ambiguous advertised channel allowed preparation");
        client = connect(services, true, false);
        check([client prepareBudsOnHandoff:peer ticket:&ticket] != 0 && fixture.opened.count == 1,
              "ordinary non-diagnostic channel allowed preparation");

        client = connect(services);
        fixture.paired = NO;
        check([client prepareBudsOnHandoff:peer ticket:&ticket] != 0 && fixture.opened.count == 1,
              "unpaired device allowed preparation");
        fixture.paired = YES;
        check([client prepareBudsOnHandoff:otherPeer ticket:&ticket] != 0 && fixture.opened.count == 1,
              "mismatched target allowed preparation");
        check([client prepareBudsOnHandoff:peer ticket:&ticket] == 0 && ticket && fixture.opened.count == 2,
              "valid diagnostic connection did not prepare a side channel");
        SimChannel *main = fixture.opened[0];
        SimChannel *side = fixture.opened[1];
        check(side.channelID == 7 && main.channelID == 4 && side.delegate != main.delegate,
              "prepared channel or receive delegate mismatched");
        char generic[] = "generic";
        [client sendData:generic length:sizeof(generic)];
        check(main.writes.count == 0 && side.writes.count == 0, "preparation or generic sends wrote data");
        [client closeBudsOnHandoff:ticket];
        check([client requestBudsOnHandoff:peer ticket:ticket] != 0 && side.writes.count == 0,
              "cancelled request sent data");

        secondary.serviceHandle = 4;
        check([client prepareBudsOnHandoff:peer ticket:&ticket] == 0, "could not re-prepare");
        side = fixture.opened.lastObject;
        secondary.serviceHandle = 5;
        check([client requestBudsOnHandoff:peer ticket:ticket] != 0 && !side.open && side.writes.count == 0,
              "service handle changed but target was still eligible");

        [client disconnect];
        client = connect(services);
        main = fixture.opened[0];
        fixture.baseband = NO;
        check([client prepareBudsOnHandoff:peer ticket:&ticket] == 0, "could not prepare new connection");
        side = fixture.opened.lastObject;
        check([client requestBudsOnHandoff:peer ticket:ticket] == 0, "one-shot setup failed");
        const UInt8 expected[] = {0xfc, 0x0e, 0x00, 0x01, 0x43, 0x04, 0x03, 0x07, 0x00,
                                  0x00, 0x0b, 0x03, 0x00, 0x00, 0x00, 0x10, 0x0f, 0xcc};
        check([side.writes isEqual:@[[NSData dataWithBytes:expected length:sizeof(expected)]]] &&
              main.writes.count == 0, "request did not send exactly the reference frame to SMEP");
        check([client requestBudsOnHandoff:peer ticket:ticket] != 0 && side.writes.count == 1,
              "repeated request wrote a second frame");
        check([client isBudsOnHandoffOpen:ticket] && side.open && side.closes == 0,
              "successful local write should leave its side channel open");
        uint64_t duplicate = 0;
        check([client prepareBudsOnHandoff:peer ticket:&duplicate] != 0 &&
              !duplicate && [client isBudsOnHandoffOpen:ticket],
              "duplicate attempt disturbed the held session");
        [client rfcommChannelClosed:(IOBluetoothRFCOMMChannel *)main];
        check([client isBudsOnHandoffOpen:ticket] && !main.open && side.open,
              "incidental primary close tore down the held channel");
        uuid_t bytes;
        [[[NSUUID alloc] initWithUUIDString:spp] getUUIDBytes:bytes];
        check([client connect:peer uuid:bytes diagnostic:diagnostic] == BT_CONN_SUCCESS &&
              [client isBudsOnHandoffOpen:ticket] && side.writes.count == 1,
              "management reconnect disturbed or rewrote the held channel");
        [client disconnectManagement];
        check([client isBudsOnHandoffOpen:ticket], "routine management disconnect disturbed held session");
        [client closeBudsOnHandoff:ticket];
        check(![client isBudsOnHandoffOpen:ticket] && !side.open && side.closes == 1,
              "explicit stop did not close the side session exactly once");

        client = connect(services);
        main = fixture.opened[0];
        check([client prepareBudsOnHandoff:peer ticket:&ticket] == 0, "could not prepare before write failure");
        side = fixture.opened.lastObject;
        side.failWrite = YES;
        check([client requestBudsOnHandoff:peer ticket:ticket] != 0 && !side.open && side.writes.count == 1,
              "failed local write reported success or left the session open");
        check([client requestBudsOnHandoff:peer ticket:ticket] != 0 && side.writes.count == 1 &&
              main.writes.count == 0, "failed write was retried or redirected");

        check([client prepareBudsOnHandoff:peer ticket:&ticket] == 0, "could not prepare before side channel loss");
        side = fixture.opened.lastObject;
        side.closeDuringWrite = YES;
        check([client requestBudsOnHandoff:peer ticket:ticket] == 8 && ![client isBudsOnHandoffOpen:ticket] &&
              side.writes.count == 1 && !side.open, "locally completed write with immediate closure lost its outcome");

        check([client prepareBudsOnHandoff:peer ticket:&ticket] == 0, "could not prepare before disconnect");
        side = fixture.opened.lastObject;
        [client disconnect];
        check(!side.open && [client requestBudsOnHandoff:peer ticket:ticket] != 0 && side.writes.count == 0,
              "disconnect left a usable handoff channel");
    }
}

int main() {
    // Match BluetoothService's background-thread entry to the synchronous API.
    std::thread worker(exerciseTransport);
    worker.join();
    return 0;
}
