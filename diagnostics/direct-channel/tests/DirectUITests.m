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
static NSUInteger setupAttempts;
static NSUInteger listenAttempts;
@implementation DirectTransport
- (NSString *)preflight { return nil; }
- (void)start:(void (^)(NSString *, NSString *))event { ++listenAttempts; }
- (void)startBookHostSetup:(void (^)(NSString *, NSString *))event {
    ++setupAttempts;
    event(@"opening", @"Opening");
}
- (void)stop { ++stops; }
@end

@interface TestController : ProbeController
@property BOOL confirm;
@property(copy) NSString *blocker;
@end
@implementation TestController
- (BOOL)confirmHostSetup { return self.confirm; }
- (NSString *)preflightBlocker { return self.blocker; }
@end

static TestController *mock(void) {
    TestController *p = [TestController new];
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

static void TestHostSetup(void) {
    TestController *host = mock();
    host.hostSetup = YES;
    host.attempted = NO;
    [host start:nil];
    assert(!host.attempted && !setupAttempts && !listenAttempts);
    host.confirm = YES;
    host.blocker = @"Missing device";
    [host start:nil];
    assert(!host.attempted && !setupAttempts && [[host reportText] containsString:@"No opening attempt"]);
    host.blocker = nil;
    [host start:nil];
    [host start:nil];
    assert(host.attempted && setupAttempts == 1 && !listenAttempts);
    [host transportStage:@"opened" detail:@"Opened"];
    assert(!host.listeningTimer && !host.stopped.enabled && !host.continued.enabled);
    assert([[host reportText] containsString:@"Setup write completion unconfirmed"]);
    [host record:host.stopped];
    assert(!host.reported && !host.ended);
    [host transportStage:@"sent" detail:@"Local write completed"];
    assert(host.ended && host.sent && !host.reported);
    assert([[host reportText] containsString:@"Mac completed one setup write"]);
    assert(![[host reportText] containsString:@"Listener observation"]);
    [host transportStage:@"closed" detail:@"Late closure"];
    assert(![[host reportText] containsString:@"Late closure"]);

    for (NSString *stage in @[@"failed", @"closed", @"timeout"]) {
        TestController *interrupted = mock();
        interrupted.hostSetup = YES;
        [interrupted transportStage:@"opened" detail:@"Opened"];
        [interrupted transportStage:stage detail:@"Write did not complete"];
        [interrupted transportStage:@"sent" detail:@"Late callback"];
        assert(interrupted.ended && !interrupted.sent);
        assert([[interrupted reportText] containsString:@"Setup write completion unconfirmed"]);
    }
    TestController *closed = mock();
    closed.hostSetup = YES;
    [closed transportStage:@"opened" detail:@"Opened"];
    [closed windowWillClose:nil];
    [closed transportStage:@"sent" detail:@"Late callback"];
    assert(closed.ended && !closed.sent && ![[closed reportText] containsString:@"Late callback"]);
    TestController *listen = mock();
    listen.attempted = NO;
    [listen start:nil];
    assert(listen.attempted && listenAttempts == 1 && setupAttempts == 1);
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
    TestHostSetup();
    puts("UI state fixtures passed");
} return 0; }
