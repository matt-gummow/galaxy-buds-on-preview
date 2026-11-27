#import "../DirectTransport.h"
#import <IOBluetooth/IOBluetooth.h>

@interface DirectTransport (TestInputs)
- (id)clientSettings;
- (NSArray *)pairedDevices;
- (void)checkTimeout;
- (void)checkWriteTimeout;
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
@property BluetoothSDPServiceRecordHandle handle;
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
- (IOReturn)getServiceRecordHandle:(BluetoothSDPServiceRecordHandle *)handle {
    *handle = self.handle;
    return self.handle ? kIOReturnSuccess : kIOReturnError;
}
@end

@class Peer;
@interface Channel : NSObject
@property(weak) id<IOBluetoothRFCOMMChannelDelegate> receiver;
@property(weak) Peer *peer;
@property BOOL isOpen;
@property BOOL isIncoming;
@property unsigned closes;
@property UInt16 mtu;
@property IOReturn queueStatus;
@property unsigned writes;
@property void *token;
@property(strong) NSData *frame;
@end
@implementation Channel
- (id)delegate { return self.receiver; }
- (IOReturn)setDelegate:(id)delegate { self.receiver = delegate; return kIOReturnSuccess; }
- (id)getDevice { return self.peer; }
- (BluetoothRFCOMMChannelID)getChannelID { return 7; }
- (UInt16)getMTU { return self.mtu; }
- (IOReturn)writeAsync:(void *)buffer length:(UInt16)length refcon:(void *)refcon {
    ++_writes;
    self.frame = [NSData dataWithBytes:buffer length:length];
    self.token = refcon;
    return self.queueStatus;
}
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
@property unsigned queries;
@end
@implementation Peer
- (id)getServiceRecordForUUID:(id)uuid { return self.lookup; }
- (IOReturn)performSDPQuery:(id)target {
    ++_queries;
    NSCAssert(NO, @"Neither mode may start service discovery");
    return kIOReturnError;
}
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
    peer.channel.mtu = 127;
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
- (void)beginSetup {
    NSMutableArray *steps = self.steps;
    [self startBookHostSetup:^(NSString *stage, NSString *detail) {
        NSCAssert(detail.length > 0, @"Setup events need a report detail");
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
    for (Peer *peer in rig.paired)
        NSCAssert(!peer.channel.writes && !peer.queries, @"The connection check never requests discovery or sends setup");
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

static void MarkSamsungService(Peer *peer) {
    uuid_t value;
    [[[NSUUID alloc] initWithUUIDString:@"F8620674-A1ED-41AB-A8B9-DE9AD655729D"] getUUIDBytes:value];
    Element *entry = [Element new], *list = [Element new];
    entry.uuid = [IOBluetoothSDPUUID uuidWithBytes:value length:sizeof(value)];
    list.children = @[entry];
    peer.lookup.classes = list;
}

static void TestBookHostSetup(void) {
    // Independently construct the two public reference implementations’ v3
    // setup: message ID + command + extended body, little-endian CRC/XMODEM.
    const uint8_t body[] = {1, 0x43, 4, 3, 7, 0, 0, 0x0b, 3, 0, 0, 0};
    uint16_t crc = 0;
    for (size_t i = 0; i < sizeof(body); ++i) {
        crc ^= (uint16_t)body[i] << 8;
        for (int bit = 0; bit < 8; ++bit)
            crc = (uint16_t)((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
    }
    uint8_t header[] = {0xfc, sizeof(body) + 2, 0};
    uint8_t trailer[] = {(uint8_t)crc, (uint8_t)(crc >> 8), 0xcc};
    NSMutableData *expected = [NSMutableData dataWithBytes:header length:sizeof(header)];
    [expected appendBytes:body length:sizeof(body)];
    [expected appendBytes:trailer length:sizeof(trailer)];

    Rig *rig = [Rig new];
    Peer *verified = PairedBuds();
    MarkSamsungService(verified);
    rig.paired = @[rig.peer, verified];
    [rig beginSetup]; Drain();
    Channel *channel = verified.channel;
    NSCAssert(!rig.peer.opens && !rig.peer.channel.writes && channel.writes == 1 &&
              [channel.frame isEqual:expected], @"Use the verified alias and send only the reference frame");
    NSCAssert(([rig.steps isEqual:@[@"opening", @"opened", @"verified", @"writing"]]), @"Queueing alone is not a confirmed write");
    [channel.receiver rfcommChannelOpenComplete:(id)channel status:kIOReturnSuccess];
    [channel.receiver rfcommChannelWriteComplete:(id)channel refcon:NULL status:kIOReturnSuccess];
    Drain();
    NSCAssert(channel.writes == 1 && [rig.steps.lastObject isEqual:@"writing"], @"Ignore duplicate open or unrelated write");
    [channel.receiver rfcommChannelWriteComplete:(id)channel refcon:channel.token status:kIOReturnSuccess];
    Drain();
    NSCAssert(([rig.steps isEqual:@[@"opening", @"opened", @"verified", @"writing", @"sent"]] && channel.closes == 1),
              @"Confirm the local write once and close its channel");
    [rig beginSetup]; Drain();
    NSCAssert(channel.writes == 1 && verified.opens == 1, @"Never retry the setup");

    rig = [Rig new]; MarkSamsungService(rig.peer);
    rig.peer.synchronous = NO; [rig beginSetup];
    rig.peer.lookup.classes = nil;
    rig.peer.channel.isOpen = YES;
    [rig.peer.channel.receiver rfcommChannelOpenComplete:(id)rig.peer.channel status:kIOReturnSuccess];
    Drain();
    NSCAssert(rig.peer.queries == 0 && rig.peer.channel.writes == 1 && [rig.peer.channel.frame isEqual:expected],
              @"The corroborated vendor service mapping remains usable after the class field disappears");
    [rig stop];

    rig = [Rig new]; MarkSamsungService(rig.peer);
    rig.peer.channel.mtu = (UInt16)expected.length - 1; [rig beginSetup]; Drain();
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && !rig.peer.channel.writes,
              @"A short MTU must not cause a partial write");

    rig = [Rig new]; MarkSamsungService(rig.peer);
    rig.peer.channel.queueStatus = kIOReturnError; [rig beginSetup]; Drain();
    NSCAssert(([rig.steps isEqual:@[@"opening", @"opened", @"verified", @"writing", @"failed"]]) &&
              rig.peer.channel.writes == 1, @"A rejected write must still be reported as an attempt");

    rig = [Rig new]; MarkSamsungService(rig.peer); [rig beginSetup]; Drain();
    channel = rig.peer.channel;
    [channel.receiver rfcommChannelWriteComplete:(id)channel refcon:channel.token status:kIOReturnSuccess
                                     bytesWritten:expected.length - 1];
    Drain();
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && channel.writes == 1, @"A partial completion is inconclusive");

    rig = [Rig new]; MarkSamsungService(rig.peer); [rig beginSetup]; Drain();
    channel = rig.peer.channel;
    [rig checkWriteTimeout];
    [(id<IOBluetoothRFCOMMChannelDelegate>)rig rfcommChannelWriteComplete:(id)channel refcon:channel.token status:kIOReturnSuccess];
    Drain();
    NSCAssert([rig.steps.lastObject isEqual:@"timeout"] && channel.writes == 1 && channel.closes == 1,
              @"A timeout must suppress late completion and never cause another write");

    for (NSString *cancelAt in @[@"opened", @"verified"]) {
        rig = [Rig new];
        __weak Rig *cancelled = rig;
        [rig startBookHostSetup:^(NSString *stage, NSString *detail) {
            (void)detail;
            [cancelled.steps addObject:stage];
            if ([stage isEqual:cancelAt]) [cancelled stop];
        }];
        Drain();
        NSCAssert([rig.steps.lastObject isEqual:cancelAt] && !rig.peer.channel.writes && rig.peer.channel.closes == 1,
                  @"A cancelled setup must close without submitting a write");
    }
}

// The open can return a different wrapper for the same address. A service
// handle identifies a record on that device even when only one wrapper has its class list.
static Rig *OpenWithAlias(Peer *livePeer, BluetoothSDPServiceRecordHandle pairedHandle) {
    Rig *rig = [Rig new];
    rig.peer.lookup.handle = pairedHandle;
    MarkSamsungService(rig.peer);
    rig.peer.channel.peer = livePeer;
    [rig beginSetup]; Drain();
    return rig;
}

static void TestOpenChannelIdentity(void) {
    Peer *live = PairedBuds();
    live.lookup.handle = 0x10011;
    Rig *rig = OpenWithAlias(live, live.lookup.handle);
    NSCAssert(rig.peer.channel.writes == 1 && !live.queries,
              @"Equivalent records on the selected Buds should authorize one write");
    [rig stop];

    live = PairedBuds();
    rig = OpenWithAlias(live, 0);
    NSCAssert(!live.queries && rig.peer.channel.writes == 1,
              @"One exact vendor UUID record with a unique channel works when both handles are absent");
    [rig stop];

    live = PairedBuds(); live.services = @[]; live.lookup = nil;
    rig = OpenWithAlias(live, 0x10011);
    NSCAssert(rig.peer.channel.writes == 1 && !live.queries,
              @"A cacheless live wrapper uses the paired mapping on the same open peer and channel");
    [rig stop];

    live = PairedBuds(); live.lookup.handle = 0x10012;
    rig = OpenWithAlias(live, 0x10011);
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && !rig.peer.channel.writes,
              @"Different known handles on the same channel must block a write");

    live = PairedBuds(); live.addressString = @"02-00-00-00-00-99";
    rig = OpenWithAlias(live, 0);
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && !rig.peer.channel.writes,
              @"An apparently matching service on a different device must never receive setup");

    live = PairedBuds();
    live.lookup.number = 11;
    rig = OpenWithAlias(live, 0x10011);
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && !live.queries && !rig.peer.channel.writes,
              @"A verified service on a different RFCOMM number cannot identify the open channel");

    live = PairedBuds();
    Record *competitor = [Record new];
    competitor.number = live.lookup.number;
    live.services = @[live.lookup, competitor];
    rig = OpenWithAlias(live, 0x10011);
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && !live.queries && !rig.peer.channel.writes,
              @"A channel claimed by two records is ambiguous");

    live = PairedBuds();
    live.lookup.matches = NO;
    live.lookup = nil;
    rig = OpenWithAlias(live, 0);
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && !rig.peer.channel.writes,
              @"A non-Samsung service claiming the open channel must override a stale paired mapping");

    rig = [Rig new]; rig.peer.lookup.handle = 0x10011;
    Peer *second = PairedBuds(); second.lookup.handle = 0x10012;
    rig.paired = @[rig.peer, second];
    [rig beginSetup]; Drain();
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && !second.channel.writes && !rig.peer.channel.writes,
              @"Two paired views identifying different records for the same service must prevent setup");

    live = PairedBuds();
    Element *list = [Element new], *otherClass = [Element new];
    otherClass.uuid = [IOBluetoothSDPUUID uuid16:0x1101]; list.children = @[otherClass];
    live.lookup.classes = list;
    live.lookup.handle = 0x10011;
    rig = OpenWithAlias(live, live.lookup.handle);
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && !live.queries && !rig.peer.channel.writes,
              @"An explicit conflicting class on the actual record overrides an agreeing alias");
}

static Rig *StartPendingSetup(void) {
    Rig *rig = [Rig new];
    rig.peer.lookup.handle = 0x10011;
    rig.peer.synchronous = NO;
    [rig beginSetup];
    return rig;
}

static void ExpectSetupRefusedOnOpen(Rig *rig) {
    Channel *channel = rig.peer.channel;
    channel.isOpen = YES;
    [channel.receiver rfcommChannelOpenComplete:(id)channel status:kIOReturnSuccess]; Drain();
    NSCAssert([rig.steps.lastObject isEqual:@"failed"] && !channel.writes && !rig.peer.queries,
              @"Changed or missing bindings must prevent setup");
}

static void TestLostOrConflictingBinding(void) {
    Rig *rig = StartPendingSetup();
    rig.peer.services = @[]; rig.peer.lookup = nil;
    ExpectSetupRefusedOnOpen(rig);

    rig = StartPendingSetup();
    rig.settings = @{};
    ExpectSetupRefusedOnOpen(rig);

    rig = StartPendingSetup();
    Record *replacement = [Record new];
    replacement.number = 7; replacement.matches = YES; replacement.handle = 0x10012;
    rig.peer.services = @[replacement]; rig.peer.lookup = replacement;
    ExpectSetupRefusedOnOpen(rig);
}

int main(void) { @autoreleasepool {
    TestDuplicatePairedRows();
    TestBookHostSetup();
    TestOpenChannelIdentity();
    TestLostOrConflictingBinding();
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
