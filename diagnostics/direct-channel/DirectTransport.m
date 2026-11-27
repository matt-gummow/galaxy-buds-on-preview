#import "DirectTransport.h"
#import <IOBluetooth/IOBluetooth.h>

typedef void (^ProbeEvent)(NSString *, NSString *);

// Galaxy Book extended v3 host setup, including the clear wire flag and
// little-endian CRC16/XMODEM over the message ID, command and payload.
// Static storage remains valid until any pending IOBluetooth write completes.
static const UInt8 BookHostSetup[] = {
    0xfc, 0x0e, 0x00, 0x01, 0x43, 0x04, 0x03, 0x07, 0x00,
    0x00, 0x0b, 0x03, 0x00, 0x00, 0x00, 0x10, 0x0f, 0xcc
};

static NSString *PeerKey(id value) {
    if (![value isKindOfClass:NSString.class] || [value length] != 17) return nil;
    NSString *address = [value uppercaseString];
    NSMutableString *key = [NSMutableString stringWithCapacity:12];
    unichar separator = [address characterAtIndex:2];
    if (separator != ':' && separator != '-') return nil;
    for (NSUInteger i = 0; i < address.length; ++i) {
        unichar ch = [address characterAtIndex:i];
        if (i % 3 == 2) {
            if (ch != separator) return nil;
        } else {
            if (!(ch >= '0' && ch <= '9') && !(ch >= 'A' && ch <= 'F')) return nil;
            [key appendFormat:@"%C", ch];
        }
    }
    return key;
}

static NSString *SelectedPeerKey(id json) {
    if (![json isKindOfClass:NSDictionary.class]) return nil;
    NSString *key = PeerKey(json[@"LastDeviceMac"]);
    if (!key || ![json[@"Devices"] isKindOfClass:NSArray.class]) return nil;
    NSUInteger matches = 0;
    for (id row in json[@"Devices"]) {
        if (![row isKindOfClass:NSDictionary.class] || ![key isEqual:PeerKey(row[@"MacAddress"])]) continue;
        if (![row[@"Model"] isEqual:@14] && ![row[@"Model"] isEqual:@"BudsOn"]) return nil;
        ++matches;
    }
    return matches == 1 ? key : nil;
}

static BOOL SameRecord(IOBluetoothSDPServiceRecord *a, IOBluetoothSDPServiceRecord *b) {
    if (!a || !b) return NO;
    if (a == b) return YES;
    BluetoothSDPServiceRecordHandle first = 0, second = 0;
    return [a getServiceRecordHandle:&first] == kIOReturnSuccess &&
           [b getServiceRecordHandle:&second] == kIOReturnSuccess && first && first == second;
}

@interface ControlService : NSObject
@property BluetoothRFCOMMChannelID number;
@property(strong) IOBluetoothSDPServiceRecord *record;
@property(copy) NSString *classIssue;
@end
@implementation ControlService
@end

static NSString *FindCachedChannel(IOBluetoothDevice *device, ControlService *service, BOOL *missing) {
    *missing = NO;
    const UInt8 bytes[] = {0xf8, 0x62, 0x06, 0x74, 0xa1, 0xed, 0x41, 0xab,
                           0xa8, 0xb9, 0xde, 0x9a, 0xd6, 0x55, 0x72, 0x9d};
    IOBluetoothSDPUUID *uuid = [IOBluetoothSDPUUID uuidWithBytes:bytes length:sizeof(bytes)];
    NSArray *records = device.services;
    if (!records.count) {
        *missing = YES;
        return @"macOS provided no cached services for the paired Buds.";
    }
    IOBluetoothSDPServiceRecord *lookup = [device getServiceRecordForUUID:uuid];
    IOBluetoothSDPServiceRecord *match = nil;
    NSUInteger matches = 0;
    unsigned uses[31] = {};
    for (IOBluetoothSDPServiceRecord *record in records) {
        BluetoothRFCOMMChannelID ch = 0;
        if ([record getRFCOMMChannelID:&ch] == kIOReturnSuccess && ch > 0 && ch <= 30) ++uses[ch];
        if ([record matchesUUIDArray:@[uuid]]) {
            match = record;
            ++matches;
        }
    }
    if (!matches && !lookup) {
        *missing = YES;
        return @"macOS could not find Samsung’s control UUID in the cached services.";
    }
    if (!matches) return @"The cached service list could not confirm the Samsung control UUID lookup.";
    if (matches > 1) return [NSString stringWithFormat:@"%lu cached records contain Samsung’s control UUID.", (unsigned long)matches];
    if (!SameRecord(match, lookup)) return @"The Samsung control UUID lookup and cached record list disagree.";
    BluetoothRFCOMMChannelID selected = 0;
    if ([match getRFCOMMChannelID:&selected] != kIOReturnSuccess || selected < 1 || selected > 30)
        return @"The matching cached record has no valid RFCOMM channel number.";
    if (uses[selected] != 1)
        return [NSString stringWithFormat:@"%u cached service records claim the channel for Samsung’s control UUID.", uses[selected]];
    // Apple searches all attributes for a UUID. Require the vendor class if
    // classes are readable. Incomplete caches can establish only a record
    // match, sufficient for this receive-only observation.
    IOBluetoothSDPDataElement *classes = [match getAttributeDataElement:kBluetoothSDPAttributeIdentifierServiceClassIDList];
    NSArray *entries = [classes getArrayValue];
    BOOL hasDecodedClass = NO;
    BOOL contains = NO;
    for (id item in entries) {
        IOBluetoothSDPUUID *value = [item isKindOfClass:IOBluetoothSDPUUID.class] ? item :
                                    ([item respondsToSelector:@selector(getUUIDValue)] ? [item getUUIDValue] : nil);
        if (![value isKindOfClass:IOBluetoothSDPUUID.class]) continue;
        hasDecodedClass = YES;
        if ([value isEqualToUUID:uuid]) contains = YES;
    }
    if (hasDecodedClass && !contains) return @"The cached service classes contradict the Samsung control UUID lookup.";
    if (!contains) {
        if (!classes) service.classIssue = @"The Samsung record has no service-class attribute.";
        else if (!entries) service.classIssue = @"The Samsung record’s service-class attribute is not a list.";
        else if (!entries.count) service.classIssue = @"The Samsung record’s service-class list is empty.";
        else service.classIssue = @"The Samsung record’s service-class list contains no decodable UUIDs.";
    }
    service.record = match;
    service.number = selected;
    return nil;
}

static BOOL ClaimsChannel(IOBluetoothDevice *device, BluetoothRFCOMMChannelID expected) {
    for (IOBluetoothSDPServiceRecord *record in device.services) {
        BluetoothRFCOMMChannelID number = 0;
        if ([record getRFCOMMChannelID:&number] == kIOReturnSuccess && number == expected) return YES;
    }
    return NO;
}

static BluetoothSDPServiceRecordHandle KnownHandle(IOBluetoothSDPServiceRecord *record) {
    BluetoothSDPServiceRecordHandle handle = 0;
    return record && [record getServiceRecordHandle:&handle] == kIOReturnSuccess ? handle : 0;
}

@interface DirectTransport () <IOBluetoothRFCOMMChannelDelegate>
@end

@implementation DirectTransport {
    IOBluetoothDevice *_peer;
    IOBluetoothRFCOMMChannel *_channel;
    BluetoothRFCOMMChannelID _number;
    NSString *_key;
    ProbeEvent _event;
    BOOL _started;
    BOOL _opened;
    BOOL _awaitingCompletion;
    BOOL _closeRequested;
    BOOL _bookHostSetup;
    IOBluetoothDevice *_queryDevice;
    BOOL _queryAttempted;
    BOOL _writeAttempted;
    BOOL _awaitingWrite;
}

// These two read-only inputs are overridden by the transport fixtures.
- (id)clientSettings {
    NSURL *dir = [NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory inDomains:NSUserDomainMask].firstObject;
    NSURL *url = [dir URLByAppendingPathComponent:@"GalaxyBudsClient/settings.json"];
    NSData *data = [NSData dataWithContentsOfURL:url];
    return data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
}

- (NSArray *)pairedDevices { return [IOBluetoothDevice pairedDevices]; }

- (NSString *)resolveKey:(NSString *)key peer:(IOBluetoothDevice **)peer number:(BluetoothRFCOMMChannelID *)selected {
    *peer = nil;
    *selected = 0;
    if (!key) return @"The client settings do not identify one selected Galaxy Buds On.";
    NSString *unavailable = @"The selected Buds On are absent from the Mac’s paired-device list. Check Bluetooth access for this diagnostic.";
    BOOL selectedHasVendorClass = NO;
    for (IOBluetoothDevice *device in [self pairedDevices]) {
        if (![key isEqual:PeerKey(device.addressString)]) continue;

        // macOS may list the same address more than once, with different cached services.
        ControlService *service = [ControlService new];
        BOOL missing;
        NSString *reason = FindCachedChannel(device, service, &missing);
        if (missing) {
            unavailable = reason;
            continue;
        }
        if (reason) return reason;
        if (*peer && *selected != service.number)
            return @"Cached records for the same Buds On disagree about Samsung’s control channel.";
        if (!*peer || (_bookHostSetup && !service.classIssue && !selectedHasVendorClass)) {
            *peer = device;
            *selected = service.number;
            selectedHasVendorClass = !service.classIssue;
        }
    }
    return *peer ? nil : unavailable;
}

- (NSString *)resolve {
    _key = SelectedPeerKey([self clientSettings]);
    IOBluetoothDevice *device = nil;
    NSString *reason = [self resolveKey:_key peer:&device number:&_number];
    _peer = device;
    return reason;
}

- (NSString *)preflight {
    NSAssert(NSThread.isMainThread, @"Call on main thread");
    if (_started) return @"This diagnostic has already run.";
    return [self resolve];
}

- (BOOL)ownsChannel:(IOBluetoothRFCOMMChannel *)channel {
    return channel && channel == _channel && channel.delegate == self && !channel.isIncoming &&
           [channel getChannelID] == _number && [_key isEqual:PeerKey([channel getDevice].addressString)];
}

// Detach only our delegate. Closing the device would also tear down its
// other Bluetooth profiles. A pending open keeps its delegate until drained.
- (void)releaseChannel {
    IOBluetoothRFCOMMChannel *channel = _channel;
    _channel = nil;
    if (channel.delegate == self) [channel setDelegate:nil];
}

- (void)stop {
    NSAssert(NSThread.isMainThread, @"Call on main thread");
    _event = nil;
    _awaitingWrite = NO;
    _queryDevice = nil;
    if (!_closeRequested && [self ownsChannel:_channel]) {
        _closeRequested = YES;
        [_channel closeChannel];
    }
    if (!_awaitingCompletion) [self releaseChannel];
}

- (void)finish:(NSString *)stage detail:(NSString *)detail {
    ProbeEvent callback = _event;
    if (_bookHostSetup && !_writeAttempted)
        detail = [detail stringByAppendingString:@" No setup write was made."];
    [self stop];
    if (callback) callback(stage, detail);
}

- (void)checkTimeout {
    if (_event && !_opened) {
        [self finish:@"timeout" detail:@"The Mac did not confirm the control channel opened before the deadline."];
    }
}

- (void)checkWriteTimeout {
    if (_event && _awaitingWrite)
        [self finish:@"timeout" detail:@"macOS did not confirm the setup write before the deadline. Its delivery is unknown."];
}

- (void)start:(ProbeEvent)event {
    [self startWithBookHostSetup:NO event:event];
}

- (void)startBookHostSetup:(ProbeEvent)event {
    [self startWithBookHostSetup:YES event:event];
}

- (void)startWithBookHostSetup:(BOOL)hostSetup event:(ProbeEvent)event {
    NSAssert(NSThread.isMainThread, @"Call on main thread");
    if (_started) { event(@"failed", @"This diagnostic has already run."); return; }
    _started = YES;
    _bookHostSetup = hostSetup;
    NSString *reason = [self resolve];
    if (reason) {
        event(@"failed", hostSetup ? [reason stringByAppendingString:@" No setup write was made."] : reason);
        return;
    }
    _event = [event copy];
    _event(@"opening", @"Opening the channel from the cached Samsung control record.");
    if (!_event) return;

    IOBluetoothRFCOMMChannel *pending = nil;
    _awaitingCompletion = YES;
    IOReturn status = [_peer openRFCOMMChannelAsync:&pending withChannelID:_number delegate:self];
    _channel = pending;
    if (status != kIOReturnSuccess || !pending) {
        _awaitingCompletion = NO;
        [self finish:@"failed" detail:[NSString stringWithFormat:@"The Mac could not start the channel open (0x%08x).", (unsigned)status]];
        return;
    }
    if (!_event) { [self stop]; return; }
    __weak DirectTransport *weakSelf = self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 12 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        [weakSelf checkTimeout];
    });
}

// Even synchronous callbacks are handled on a later turn, after the SDK
// has supplied its channel object. Incoming data is intentionally discarded.
- (void)rfcommChannelData:(IOBluetoothRFCOMMChannel *)channel data:(void *)bytes length:(size_t)length {}

// Separate a lack of class evidence (eligible for one live query) from an
// incompatible record or channel (terminal). Re-read the pairing, open
// channel and service records on every pass, including after discovery.
- (NSString *)verifySetupChannel:(IOBluetoothRFCOMMChannel *)channel incomplete:(NSString **)incomplete {
    *incomplete = nil;
    if (![_key isEqual:SelectedPeerKey([self clientSettings])])
        return @"The selected Galaxy Buds On changed before setup.";
    if (![self ownsChannel:channel] || !channel.isOpen)
        return @"The selected outgoing control channel is no longer open and owned by this check.";

    IOBluetoothDevice *live = [channel getDevice];
    ControlService *opened = [ControlService new];
    BOOL missing;
    NSString *reason = FindCachedChannel(live, opened, &missing);
    if (reason && !missing) return reason;
    if (missing && ClaimsChannel(live, _number))
        return @"A different service on the open device claims the selected RFCOMM channel.";
    if (!missing && opened.number != _number)
        return @"The live Samsung service now identifies a different RFCOMM channel.";

    NSString *liveIssue = missing ? reason : opened.classIssue;
    BOOL verified = opened.record && !opened.classIssue;
    BOOL paired = NO, pairedChannel = NO;
    BluetoothSDPServiceRecordHandle agreedHandle = KnownHandle(opened.record);
    for (IOBluetoothDevice *device in [self pairedDevices]) {
        if (![_key isEqual:PeerKey(device.addressString)]) continue;
        paired = YES;
        ControlService *other = opened;
        if (device != live) {
            other = [ControlService new];
            BOOL aliasMissing;
            NSString *aliasReason = FindCachedChannel(device, other, &aliasMissing);
            if (aliasMissing) {
                if (ClaimsChannel(device, _number))
                    return @"A paired record assigns the open channel to a different service.";
                continue;
            }
            if (aliasReason) return aliasReason;
        }
        if (!other.record) continue;
        if (other.number != _number)
            return @"The paired Samsung service identifies a different RFCOMM channel.";
        pairedChannel = YES;
        BluetoothSDPServiceRecordHandle handle = KnownHandle(other.record);
        if (handle && agreedHandle && agreedHandle != handle)
            return @"Paired records for the open channel have conflicting Samsung service handles.";
        if (handle) agreedHandle = handle;
        if (!other.classIssue && SameRecord(opened.record, other.record)) verified = YES;
    }
    if (!paired) return @"The selected Buds are no longer in the paired-device list.";
    if (!opened.record && !pairedChannel)
        return @"Neither the open device nor a paired record identifies Samsung’s service on the selected channel.";
    if (!verified) *incomplete = liveIssue ?: @"The open channel’s Samsung service identity is unconfirmed.";
    return nil;
}

- (void)checkServiceQueryTimeout {
    if (_queryDevice && _event)
        [self finish:@"timeout" detail:@"macOS did not finish the service lookup before the deadline."];
}

- (void)refreshServices:(IOBluetoothRFCOMMChannel *)channel {
    _queryAttempted = YES;
    _queryDevice = [channel getDevice];
    _event(@"discovering", @"Requesting fresh service records for the selected Buds on the open connection.");
    if (!_event || !_queryDevice) return;
    if (![self ownsChannel:channel] || !channel.isOpen) {
        [self finish:@"failed" detail:@"The selected control channel changed before service discovery."];
        return;
    }
    // The unfiltered search requests all attributes of all L2CAP services,
    // including potential competing records for this RFCOMM channel.
    IOReturn status = [_queryDevice performSDPQuery:self];
    if (status != kIOReturnSuccess) {
        [self finish:@"failed" detail:[NSString stringWithFormat:@"macOS could not start service discovery (0x%08x).", (unsigned)status]];
        return;
    }
    __weak DirectTransport *weakSelf = self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        [weakSelf checkServiceQueryTimeout];
    });
}

- (void)sdpQueryComplete:(IOBluetoothDevice *)device status:(IOReturn)status {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!self->_event || !self->_queryDevice || device != self->_queryDevice) return;
        self->_queryDevice = nil; // Consume this completion before any listener or transport call.
        if (status != kIOReturnSuccess) {
            [self finish:@"failed" detail:[NSString stringWithFormat:@"Service discovery failed (0x%08x).", (unsigned)status]];
            return;
        }
        [self sendBookHostSetup:self->_channel];
    });
}

- (void)sendBookHostSetup:(IOBluetoothRFCOMMChannel *)channel {
    if (!_event || _queryDevice || _writeAttempted) return;
    NSString *incomplete = nil;
    NSString *reason = [self verifySetupChannel:channel incomplete:&incomplete];
    if (reason) {
        [self finish:@"failed" detail:reason];
        return;
    }
    if (incomplete) {
        if (_queryAttempted)
            [self finish:@"failed" detail:[@"After service discovery: " stringByAppendingString:incomplete]];
        else
            [self refreshServices:channel];
        return;
    }
    if ([channel getMTU] < sizeof(BookHostSetup)) {
        [self finish:@"failed" detail:@"The complete host setup does not fit in one channel write."];
        return;
    }
    // Consume this attempt before calling the SDK. No callback or failed
    // queue operation can start a second write.
    _writeAttempted = YES;
    _awaitingWrite = YES;
    IOReturn status = [channel writeAsync:(void *)BookHostSetup length:sizeof(BookHostSetup) refcon:(__bridge void *)self];
    if (!_event) return;
    _event(@"writing", @"The Mac attempted the single Galaxy Book host setup write.");
    if (!_event) return;
    if (status != kIOReturnSuccess) {
        [self finish:@"failed" detail:[NSString stringWithFormat:@"macOS could not queue the setup write (0x%08x).", (unsigned)status]];
        return;
    }
    __weak DirectTransport *weakSelf = self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        [weakSelf checkWriteTimeout];
    });
}

- (void)rfcommChannelWriteComplete:(IOBluetoothRFCOMMChannel *)channel refcon:(void *)refcon status:(IOReturn)status {
    // The original delegate callback supplies only the I/O status.
    [self rfcommChannelWriteComplete:channel refcon:refcon status:status bytesWritten:sizeof(BookHostSetup)];
}

- (void)rfcommChannelWriteComplete:(IOBluetoothRFCOMMChannel *)channel refcon:(void *)refcon
                            status:(IOReturn)status bytesWritten:(size_t)length {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (channel != self->_channel || refcon != (__bridge void *)self || !self->_awaitingWrite) return;
        if (status != kIOReturnSuccess || length != sizeof(BookHostSetup)) {
            [self finish:@"failed" detail:@"macOS did not confirm the full setup write. Its delivery is unknown."];
            return;
        }
        [self finish:@"sent" detail:@"macOS completed the Galaxy Book host setup write. Earbud acceptance is unconfirmed."];
    });
}

- (void)rfcommChannelOpenComplete:(IOBluetoothRFCOMMChannel *)channel status:(IOReturn)status {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (channel != self->_channel || !self->_awaitingCompletion) return;
        self->_awaitingCompletion = NO;
        if (!self->_event) {
            if (status == kIOReturnSuccess && channel.isOpen) self->_closeRequested = NO;
            [self stop]; // A late success after cancel or timeout is closed.
            return;
        }
        if (status != kIOReturnSuccess || ![self ownsChannel:channel] || !channel.isOpen) {
            [self finish:@"failed" detail:@"The Mac could not confirm the selected outgoing control channel opened."];
            return;
        }
        self->_opened = YES;
        self->_event(@"opened", self->_bookHostSetup ? @"The selected outgoing channel opened." :
                     @"The selected outgoing channel opened. No application data was sent.");
        if (self->_bookHostSetup) [self sendBookHostSetup:channel];
    });
}

- (void)rfcommChannelClosed:(IOBluetoothRFCOMMChannel *)channel {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (channel != self->_channel) return;
        if (self->_awaitingCompletion) {
            // Preserve the SDK delegate to drain a late open after an early
            // close (including one triggered by stop). The instance is single-use.
            ProbeEvent callback = self->_event;
            self->_event = nil;
            if (callback) callback(@"failed", self->_bookHostSetup ?
                                   @"The channel closed before the Mac confirmed it opened. No setup write was made." :
                                   @"The channel closed before the Mac confirmed it opened.");
            return;
        }
        [self releaseChannel];
        [self finish:@"closed" detail:self->_awaitingWrite ? @"The channel closed before macOS confirmed the setup write." :
                     @"The control channel closed."];
    });
}

- (void)dealloc {
    BOOL owned = [self ownsChannel:_channel];
    if (_channel.delegate == self) [_channel setDelegate:nil];
    if (owned) [_channel closeChannel];
}

@end
