#import "../DirectTransport.h"
#import <IOBluetooth/IOBluetooth.h>

@interface DirectTransport (TestInputs)
- (id)clientSettings;
- (NSArray *)pairedDevices;
- (void)checkTimeout;
@end

@interface Element : NSObject
@property(strong) NSArray *children;
@property(strong) IOBluetoothSDPUUID *uuid;
@end
@implementation Element
- (NSArray *)getArrayValue { return self.children; }
- (IOBluetoothSDPUUID *)getUUIDValue { return self.uuid; }
@end

@interface Record : NSObject
@property BOOL matches;
@property BluetoothRFCOMMChannelID number;
@property(strong) Element *classes;
@end
@implementation Record
- (BOOL)matchesUUIDArray:(NSArray *)uuids {
    // Independent expected service UUID: an incorrect literal fails the happy path.
    IOBluetoothSDPUUID *query = [uuids firstObject];
    uuid_t raw;
    [[[NSUUID alloc] initWithUUIDString:@"F8620674-A1ED-41AB-A8B9-DE9AD655729D"] getUUIDBytes:raw];
    return self.matches && [query isEqualToData:[NSData dataWithBytes:raw length:16]];
}
- (IOReturn)getRFCOMMChannelID:(BluetoothRFCOMMChannelID *)number {
    *number = self.number;
    return self.number ? kIOReturnSuccess : kIOReturnError;
}
- (id)getAttributeDataElement:(BluetoothSDPServiceAttributeID)attribute {
    NSCAssert(attribute == kBluetoothSDPAttributeIdentifierServiceClassIDList, @"Wrong class attribute");
    return self.classes;
}
- (IOReturn)getServiceRecordHandle:(BluetoothSDPServiceRecordHandle *)handle { return kIOReturnError; }
@end

@class Peer;
@interface Channel : NSObject
@property(weak) id<IOBluetoothRFCOMMChannelDelegate> receiver;
@property(weak) Peer *peer;
@property BOOL isOpen;
@property BOOL isIncoming;
@property unsigned closes;
@end
@implementation Channel
- (id)delegate { return self.receiver; }
- (IOReturn)setDelegate:(id)delegate { self.receiver = delegate; return kIOReturnSuccess; }
- (id)getDevice { return self.peer; }
- (BluetoothRFCOMMChannelID)getChannelID { return 7; }
- (IOReturn)closeChannel { ++_closes; self.isOpen = NO; return kIOReturnSuccess; }
@end

@interface Peer : NSObject
@property(strong) NSArray *services;
@property(strong) Record *lookup;
@property(strong) Channel *channel;
@property(copy) NSString *addressString;
@property BOOL synchronous;
@property BOOL openError;
@property unsigned opens;
@end
@implementation Peer
- (id)getServiceRecordForUUID:(id)uuid { return self.lookup; }
- (IOReturn)openRFCOMMChannelAsync:(IOBluetoothRFCOMMChannel **)output withChannelID:(BluetoothRFCOMMChannelID)number delegate:(id)delegate {
    NSCAssert(number == 7, @"Unexpected channel");
    ++_opens;
    if (_openError) return kIOReturnError;
    self.channel.receiver = delegate;
    *output = (id)self.channel;
    if (_synchronous) {
        self.channel.isOpen = YES;
        [delegate rfcommChannelOpenComplete:(id)self.channel status:kIOReturnSuccess];
    }
    return kIOReturnSuccess;
}
@end

static Peer *PairedBuds(void) {
    Peer *peer = [Peer new];
    peer.addressString = @"01-AB-02-CD-03-EF";
    Record *selected = [Record new];
    selected.number = 7;
    selected.matches = YES;
    peer.lookup = selected;
    peer.services = @[selected];
    peer.channel = [Channel new];
    peer.channel.peer = peer;
    peer.synchronous = YES;
    return peer;
}

@interface Rig : DirectTransport
@property(strong) Peer *peer;
@property(strong) id settings;
@property(strong) NSArray *paired;
@property(strong) NSMutableArray *steps;
@end
@implementation Rig
- (instancetype)init {
    if ((self = [super init])) {
        _peer = PairedBuds();
        _paired = @[_peer];
        NSString *address = @"01:ab:02:cd:03:ef";
        _settings = @{@"LastDeviceMac":address, @"Devices":@[@{@"Model":@14, @"MacAddress":address}]};
        _steps = [NSMutableArray array];
    }
    return self;
}
- (id)clientSettings { return _settings; }
- (NSArray *)pairedDevices { return _paired; }
- (void)begin {
    NSMutableArray *steps = self.steps;
    [self start:^(NSString *stage, NSString *detail) {
        NSCAssert(detail.length > 0 && ![detail containsString:@"01:ab"] && ![detail containsString:@"01-AB"], @"Unsanitized result");
        [steps addObject:stage];
    }];
}
@end

static void Drain(void) {
    [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
}
static void Refused(Rig *rig) {
    NSCAssert([rig preflight] != nil, @"Ambiguous baseline should fail");
    [rig begin];
    NSCAssert(rig.peer.opens == 0 && [rig.steps isEqual:@[@"failed"]], @"Should refuse without opening");
}

static void ExpectOpen(Rig *rig) {
    NSCAssert(![rig preflight], @"Expected a usable cached service");
    for (Peer *peer in rig.paired) {
        NSCAssert(!peer.opens, @"Preflight must be passive");
    }
    [rig begin];
    Drain();
    NSCAssert(([rig.steps isEqual:@[@"opening", @"opened"]]), @"Expected one confirmed channel open");
    [rig stop];
}

static void TestDuplicatePairedRows(void) {
    Rig *rig = [Rig new];
    rig.paired = @[rig.peer, rig.peer];
    ExpectOpen(rig);
    NSCAssert(rig.peer.opens == 1, @"Duplicate references should result in one open");

    rig = [Rig new];
    Peer *alias = PairedBuds();
    alias.addressString = @"01:ab:02:cd:03:ef";
    rig.paired = @[rig.peer, alias];
    ExpectOpen(rig);
    NSCAssert(rig.peer.opens + alias.opens == 1, @"Equivalent paired rows should result in one open");

    for (unsigned aliasFirst = 0; aliasFirst < 2; ++aliasFirst) {
        rig = [Rig new];
        alias = PairedBuds();
        alias.services = @[];
        alias.lookup = nil;
        rig.paired = aliasFirst ? @[alias, rig.peer] : @[rig.peer, alias];
        ExpectOpen(rig);
        NSCAssert(rig.peer.opens == 1 && !alias.opens, @"Only the row with the verified service may open");

        rig = [Rig new];
        alias = PairedBuds();
        alias.lookup.number = 11;
        rig.paired = aliasFirst ? @[alias, rig.peer] : @[rig.peer, alias];
        Refused(rig);
        NSCAssert(!alias.opens, @"Conflicting cached channel numbers must prevent both opens");

        rig = [Rig new];
        alias = PairedBuds();
        Record *competingService = [Record new];
        competingService.number = alias.lookup.number;
        alias.services = @[alias.lookup, competingService];
        rig.paired = aliasFirst ? @[alias, rig.peer] : @[rig.peer, alias];
        Refused(rig);
        NSCAssert(!alias.opens, @"A contradictory cache must not be treated as missing");
    }
}

int main(void) { @autoreleasepool {
    TestDuplicatePairedRows();
    Rig *rig = [Rig new];
    NSCAssert(![rig preflight] && !rig.peer.opens, @"Preflight must be passive");
    [rig begin]; Drain();
    NSCAssert(([rig.steps isEqual:@[@"opening", @"opened"]]), @"Synchronous callback");
    [rig stop]; [rig stop];
    NSCAssert(rig.peer.channel.closes == 1, @"Close once");
    rig = [Rig new]; rig.paired = @[]; Refused(rig);
    rig = [Rig new];
    rig.settings = @{@"LastDeviceMac":@"01:ab:02:cd:03:ef", @"Devices":@[@{@"Model":@13, @"MacAddress":@"01:ab:02:cd:03:ef"}]};
    Refused(rig);
    rig = [Rig new];
    NSDictionary *row = [rig.settings[@"Devices"] firstObject];
    rig.settings = @{@"LastDeviceMac":row[@"MacAddress"], @"Devices":@[row, row]};
    Refused(rig);
    rig = [Rig new]; rig.peer.lookup = nil; Refused(rig);
    rig = [Rig new]; rig.peer.lookup.number = 31; Refused(rig);
    rig = [Rig new];
    Record *other = [Record new]; other.number = 7;
    rig.peer.services = @[other, rig.peer.lookup]; Refused(rig);
    rig = [Rig new];
    other = [Record new]; other.number = 11; other.matches = YES;
    rig.peer.services = @[rig.peer.lookup, other]; Refused(rig);
    rig = [Rig new];
    Element *list = [Element new], *wrong = [Element new];
    wrong.uuid = [IOBluetoothSDPUUID uuid16:0x1101]; list.children = @[wrong];
    rig.peer.lookup.classes = list; Refused(rig);
    rig = [Rig new]; rig.peer.openError = YES; [rig begin];
    NSCAssert(([rig.steps isEqual:@[@"opening", @"failed"]]), @"Open start error");
    rig = [Rig new]; rig.peer.synchronous = NO; [rig begin]; [rig checkTimeout];
    Channel *late = rig.peer.channel; late.isOpen = YES;
    [late.receiver rfcommChannelOpenComplete:(id)late status:kIOReturnSuccess]; Drain();
    NSCAssert(([rig.steps isEqual:@[@"opening", @"timeout"]] && !late.isOpen && !late.receiver), @"Late success must close silently");
    rig = [Rig new]; rig.peer.synchronous = NO; [rig begin];
    Channel *early = rig.peer.channel;
    [early.receiver rfcommChannelClosed:(id)early]; Drain();
    early.isOpen = YES;
    [early.receiver rfcommChannelOpenComplete:(id)early status:kIOReturnSuccess]; Drain();
    NSCAssert(([rig.steps isEqual:@[@"opening", @"failed"]] && !early.isOpen && !early.receiver), @"Late success after early closure must drain");
    rig = [Rig new]; rig.peer.channel.isIncoming = YES; [rig begin]; Drain();
    NSCAssert(([rig.steps isEqual:@[@"opening", @"failed"]] && !rig.peer.channel.closes), @"Never close an incoming channel");
    rig = [Rig new]; [rig begin]; Drain();
    Channel *closed = rig.peer.channel;
    [closed.receiver rfcommChannelClosed:(id)closed]; Drain();
    NSCAssert(([rig.steps isEqual:@[@"opening", @"opened", @"closed"]]), @"Remote closure recorded");
    puts("Direct transport fixtures passed.");
} return 0; }
