// This fixture never starts NSApplication and replaces the Bluetooth transport.
#define main PROBE_MAIN
#import "../main.m"
#undef main
#import <assert.h>

@interface MockControl : NSObject
@property(getter=isEnabled) BOOL enabled;
@property(copy) NSString *title;
@property(copy) NSString *stringValue;
@end
@implementation MockControl @end
static NSUInteger stops;
@implementation DirectTransport
- (NSString *)preflight { return nil; }
- (void)start:(void (^)(NSString *, NSString *))event { abort(); }
- (void)stop { ++stops; }
@end

static ProbeController *mock(void) {
    ProbeController *p = [ProbeController new];
    p.status = (id)[MockControl new];
    p.continued = (id)[MockControl new];
    p.stopped = (id)[MockControl new];
    p.unsure = (id)[MockControl new];
    p.reportButton = (id)[MockControl new];
    p.stopped.title = @"Music stopped";
    p.continued.title = @"Music kept playing";
    p.transport = [DirectTransport new]; p.events = [NSMutableArray new];
    p.startTime = NSProcessInfo.processInfo.systemUptime;
    p.attempted = YES;
    [p updateChoices];
    return p;
}

int main(void) { @autoreleasepool {
    ProbeController *pre = mock();
    assert(!pre.continued.enabled && pre.stopped.enabled);
    [pre record:pre.stopped];
    assert(stops == 1);
    [pre transportStage:@"opened" detail:@"late"];
    assert(pre.ended && pre.reported && !pre.opened && !pre.stopped.enabled);
    assert([pre.status.stringValue containsString:@"unconfirmed"]);
    ProbeController *ok = mock();
    [ok transportStage:@"opened" detail:@"opened"];
    assert(ok.opened && !ok.continued.enabled);
    ok.openedTime -= 4;
    [ok tick];
    assert(ok.continued.enabled);
    ok.openedTime -= 12;
    [ok tick];
    assert(stops == 2 && ok.ended && !ok.reported);
    [ok record:ok.continued];
    assert(ok.reported && [ok.status.stringValue containsString:@"Channel opened"]);
    ProbeController *failed = mock();
    [failed transportStage:@"failed" detail:@"No cached service"];
    assert(failed.ended && !failed.opened && failed.continued.enabled);
    [failed record:failed.continued];
    assert([failed.status.stringValue containsString:@"unconfirmed"]);
    puts("UI state fixtures passed");
} return 0; }
