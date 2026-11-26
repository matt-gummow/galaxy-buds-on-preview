#import <Foundation/Foundation.h>
#import <CoreAudio/CoreAudio.h>
#import <IOBluetooth/IOBluetooth.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

// Observe macOS state only. Bluetooth names and addresses are never part of a sample.
static NSString *canonicalAddress(NSString *value) {
    if (value.length != 17) return nil;
    NSString *upper = [value uppercaseString];
    unichar separator = [upper characterAtIndex:2];
    if (separator != ':' && separator != '-') return nil;
    for (NSUInteger i = 0; i < upper.length; i++) {
        unichar c = [upper characterAtIndex:i];
        if (i % 3 == 2) {
            if (c != separator) return nil;
        } else if (!(('0' <= c && c <= '9') || ('A' <= c && c <= 'F'))) {
            return nil;
        }
    }
    NSString *result = [upper stringByReplacingOccurrencesOfString:@"-" withString:@":"];
    if ([result isEqualToString:@"00:00:00:00:00:00"] || [result isEqualToString:@"FF:FF:FF:FF:FF:FF"]) return nil;
    return result;
}

static BOOL isBudsName(NSString *value) {
    if (!value.length) return NO;
    NSString *name = [value stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    NSString *pattern = @"^(?:(?:[^\\r\\n]+['’]s\\s+)?(?:Galaxy\\s+)?Buds\\s+On|SM-U600)(?:\\s*\\([0-9a-f]{4}\\))?$";
    NSRange match = [name rangeOfString:pattern options:NSRegularExpressionSearch | NSCaseInsensitiveSearch];
    return match.location == 0 && match.length == name.length;
}

static NSString *findTarget(void) {
    NSString *found = nil;
    for (IOBluetoothDevice *device in [IOBluetoothDevice pairedDevices]) {
        if (!isBudsName([device name])) continue;
        NSString *address = canonicalAddress([device addressString]);
        if (!address || (found && ![found isEqualToString:address])) return nil;
        found = address;
    }
    return found;
}

static BOOL readNumber(AudioObjectID object, AudioObjectPropertySelector selector, UInt32 *value) {
    AudioObjectPropertyAddress key = {selector, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    UInt32 bytes = sizeof(*value);
    return AudioObjectGetPropertyData(object, &key, 0, NULL, &bytes, value) == noErr && bytes == sizeof(*value);
}

static NSString *deviceUid(AudioObjectID device) {
    AudioObjectPropertyAddress key = {kAudioDevicePropertyDeviceUID, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    CFStringRef uid = NULL;
    UInt32 bytes = sizeof(uid);
    if (AudioObjectGetPropertyData(device, &key, 0, NULL, &bytes, &uid) != noErr || !uid) return nil;
    return CFBridgingRelease(uid);
}

static const char *classifyRoute(UInt32 transport, NSString *uid, NSString *target, BOOL input) {
    if (transport == kAudioDeviceTransportTypeBluetooth || transport == kAudioDeviceTransportTypeBluetoothLE) {
        NSString *suffix = input ? @":input" : @":output";
        NSString *base = uid;
        if ([uid.lowercaseString hasSuffix:suffix]) base = [uid substringToIndex:uid.length - suffix.length];
        NSString *address = canonicalAddress(base);
        if (!address) return "unknown";
        if ([address isEqualToString:target]) return "buds";
        return transport == kAudioDeviceTransportTypeBluetooth ? "other" : "unknown";
    }
    // Aggregates, virtual devices, and unspecified transports may route onward to the Buds.
    switch (transport) {
        case kAudioDeviceTransportTypeBuiltIn:
        case kAudioDeviceTransportTypeDisplayPort:
        case kAudioDeviceTransportTypeHDMI:
        case kAudioDeviceTransportTypeUSB:
        case kAudioDeviceTransportTypeAirPlay: return "other";
        default: return "unknown";
    }
}

static const char *defaultRoute(NSString *target, BOOL input) {
    UInt32 device = kAudioObjectUnknown, transport = 0;
    AudioObjectPropertySelector selector = input ? kAudioHardwarePropertyDefaultInputDevice : kAudioHardwarePropertyDefaultOutputDevice;
    if (!readNumber(kAudioObjectSystemObject, selector, &device) || device == kAudioObjectUnknown ||
        !readNumber(device, kAudioDevicePropertyTransportType, &transport)) return "unknown";
    NSString *uid = nil;
    if (transport == kAudioDeviceTransportTypeBluetooth || transport == kAudioDeviceTransportTypeBluetoothLE) uid = deviceUid(device);
    return classifyRoute(transport, uid, target, input);
}

static long long epochMilliseconds(void) {
    return (long long)([[NSDate date] timeIntervalSince1970] * 1000.0);
}

@interface BudsWatch : NSObject
@property(nonatomic, copy) NSString *target;
@property(nonatomic, strong) IOBluetoothDevice *device;
@property(nonatomic, strong) IOBluetoothUserNotification *onConnect;
@property(nonatomic, strong) IOBluetoothUserNotification *onDisconnect;
@end

@implementation BudsWatch
- (void)startEvents {
    self.onConnect = [IOBluetoothDevice registerForConnectNotifications:self selector:@selector(connected:device:)];
    if (!self.onDisconnect && [self.device isConnected])
        self.onDisconnect = [self.device registerForDisconnectNotification:self selector:@selector(disconnected:device:)];
}
- (void)connected:(IOBluetoothUserNotification *)notification device:(IOBluetoothDevice *)device {
    if (![self.target isEqualToString:canonicalAddress([device addressString])]) return;
    self.device = device;
    printf("%lld event connected\n", epochMilliseconds());
    if (self.onDisconnect) [self.onDisconnect unregister];
    self.onDisconnect = [device registerForDisconnectNotification:self selector:@selector(disconnected:device:)];
}
- (void)disconnected:(IOBluetoothUserNotification *)notification device:(IOBluetoothDevice *)device {
    if (![self.target isEqualToString:canonicalAddress([device addressString])]) return;
    printf("%lld event disconnected\n", epochMilliseconds());
    if (notification == self.onDisconnect) {
        [self.onDisconnect unregister];
        self.onDisconnect = nil;
    }
}
- (void)sample {
    const char *link = "unknown";
    if (self.device && [self.device isPaired] && [IOBluetoothHostController defaultController] != nil)
        link = [self.device isConnected] ? "connected" : "disconnected";
    printf("%lld sample %s %s %s\n", epochMilliseconds(), link,
           defaultRoute(self.target, NO), defaultRoute(self.target, YES));
}
@end

static int selftest(void) {
    NSString *target = @"A0:12:34:56:78:9A";
    if (!isBudsName(@"Matthew's Buds On") || !isBudsName(@"Matt’s Galaxy Buds On (FA13)") ||
        !isBudsName(@"SM-U600") || isBudsName(@"My Galaxy Buds On backup") || isBudsName(@"Buds2 Pro")) return 1;
    if (![canonicalAddress(@"a0-12-34-56-78-9a") isEqualToString:target] ||
        canonicalAddress(@"a0:12:34:56-78:9a") || canonicalAddress(@"XX:XX:34:56:78:9A")) return 1;
    if (strcmp(classifyRoute(kAudioDeviceTransportTypeBluetooth, @"a0-12-34-56-78-9a:output", target, NO), "buds") ||
        strcmp(classifyRoute(kAudioDeviceTransportTypeBluetooth, @"A0:12:34:56:78:9A:input", target, YES), "buds") ||
        strcmp(classifyRoute(kAudioDeviceTransportTypeBluetooth, @"A0:12:34:56:78:9B:output", target, NO), "other") ||
        strcmp(classifyRoute(kAudioDeviceTransportTypeBluetooth, @"unknown", target, NO), "unknown") ||
        strcmp(classifyRoute(kAudioDeviceTransportTypeBluetoothLE, @"A0:12:34:56:78:9B", target, NO), "unknown") ||
        strcmp(classifyRoute(kAudioDeviceTransportTypeBuiltIn, nil, target, NO), "other") ||
        strcmp(classifyRoute(kAudioDeviceTransportTypeVirtual, @"A0:12:34:56:78:9A:output", target, NO), "unknown")) return 1;
    puts("Mac target selection and audio route tests passed.");
    return 0;
}

static volatile sig_atomic_t shouldStop = 0;
static void stopWatch(int sig) { (void)sig; shouldStop = 1; }

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc != 2) return 64;
        if (strcmp(argv[1], "clock") == 0) { printf("%lld\n", epochMilliseconds()); return 0; }
        if (strcmp(argv[1], "selftest") == 0) return selftest();
        if (strcmp(argv[1], "target") == 0) {
            // The caller must capture this value in memory rather than printing it to a terminal.
            if (isatty(STDOUT_FILENO)) return 64;
            NSString *address = findTarget();
            if (!address) return 2;
            puts(address.UTF8String);
            return 0;
        }
        BOOL watch = strcmp(argv[1], "watch") == 0;
        if (!watch && strcmp(argv[1], "sample") != 0) return 64;
        char buffer[40] = {0};
        if (!fgets(buffer, sizeof(buffer), stdin)) return 2;
        buffer[strcspn(buffer, "\r\n")] = 0;
        BudsWatch *probe = [BudsWatch new];
        probe.target = canonicalAddress([NSString stringWithUTF8String:buffer]);
        if (!probe.target) return 2;
        for (IOBluetoothDevice *device in [IOBluetoothDevice pairedDevices]) {
            if ([probe.target isEqualToString:canonicalAddress([device addressString])]) { probe.device = device; break; }
        }
        setvbuf(stdout, NULL, _IOLBF, 0);
        if (!watch) { [probe sample]; return 0; }
        signal(SIGTERM, stopWatch);
        signal(SIGINT, stopWatch);
        [probe startEvents];
        while (!shouldStop) {
            @autoreleasepool {
                [probe sample];
                NSDate *next = [NSDate dateWithTimeIntervalSinceNow:0.5];
                [[NSRunLoop currentRunLoop] runUntilDate:next];
                // Foundation can return early when notification registration supplied no run-loop source.
                if (!shouldStop && next.timeIntervalSinceNow > 0) [NSThread sleepUntilDate:next];
            }
        }
        [probe.onDisconnect unregister];
        [probe.onConnect unregister];
        return 0;
    }
}
