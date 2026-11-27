// This fixture never starts NSApplication and replaces the Bluetooth transport.
#define main PROBE_MAIN
#import "../main.m"
#undef main
#import <assert.h>

@interface MockControl : NSObject
@property(getter=isEnabled) BOOL enabled;
@property(getter=isHidden) BOOL hidden;
@property NSInteger selectedSegment;
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
    p.mode = (id)[MockControl new];
    p.instructions = (id)[MockControl new];
    p.choices = (id)[MockControl new];
    p.startButton = (id)[MockControl new];
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

static void TestModeSelection(void) {
    TestController *p = mock();
    p.attempted = NO;
    p.mode.selectedSegment = 0;
    [p selectMode:p.mode];
    assert(!p.hostSetup && !p.choices.hidden);
    assert([p.startButton.title isEqualToString:@"Test while Fold music is playing"]);
    p.mode.selectedSegment = 1;
    [p selectMode:p.mode];
    assert(p.hostSetup && p.choices.hidden);
    assert([p.startButton.title isEqualToString:@"Set up this Mac…"]);
    p.attempted = YES;
    p.mode.selectedSegment = 0;
    [p selectMode:p.mode];
    assert(p.hostSetup);
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
    assert([[host reportText] containsString:@"No setup write was attempted"]);
    assert([host.status.stringValue containsString:@"No setup write was attempted"]);
    host.blocker = nil;
    [host start:nil];
    [host start:nil];
    assert(host.attempted && setupAttempts == 1 && !listenAttempts);
    assert(!host.mode.enabled && !host.startButton.enabled);
    assert(!host.ended && !host.opened && !host.controlServiceVerified && !host.writeAttempted);
    assert([[host reportText] containsString:@"Samsung control service verified: unconfirmed"]);
    assert([[host reportText] containsString:@"No setup write has been attempted"]);
    [host transportStage:@"opened" detail:@"Opened"];
    assert(!host.listeningTimer && !host.stopped.enabled && !host.continued.enabled);
    assert(!host.controlServiceVerified && !host.writeAttempted);
    [host transportStage:@"verified" detail:@"The selected cached Samsung service matches the opened RFCOMM channel"];
    assert(host.controlServiceVerified && !host.writeAttempted && !host.sent && !host.ended);
    assert([host.status.stringValue containsString:@"Samsung control service verified"]);
    assert([[host reportText] containsString:@"Samsung control service verified: yes"]);
    assert([[host reportText] containsString:@"No setup write has been attempted"]);
    [host transportStage:@"writing" detail:@"Local write attempted"];
    assert(host.writeAttempted && !host.sent && !host.ended);
    assert([[host reportText] containsString:@"Setup write completion unconfirmed"]);
    [host record:host.stopped];
    assert(!host.reported && !host.ended);
    [host transportStage:@"sent" detail:@"Local write completed"];
    assert(host.ended && host.sent && !host.reported);
    assert([[host reportText] containsString:@"macOS completed one setup write"]);
    assert([host.status.stringValue containsString:@"macOS completed the setup write"]);
    assert([[host reportText] containsString:@"Earbud acceptance and audio behavior remain unverified"]);
    assert([host.status.stringValue containsString:@"Earbud acceptance is unverified"]);
    assert(![[host reportText] containsString:@"Listener observation"]);
    [host transportStage:@"closed" detail:@"Late closure"];
    assert(![[host reportText] containsString:@"Late closure"]);

    for (NSString *stage in @[@"failed", @"closed", @"timeout"]) {
        TestController *interrupted = mock();
        interrupted.hostSetup = YES;
        [interrupted transportStage:@"opened" detail:@"Opened"];
        [interrupted transportStage:@"verified" detail:@"Selected Samsung service verified"];
        [interrupted transportStage:@"writing" detail:@"Local write attempted"];
        [interrupted transportStage:stage detail:@"Write did not complete"];
        [interrupted transportStage:@"sent" detail:@"Late callback"];
        assert(interrupted.ended && !interrupted.sent);
        assert([[interrupted reportText] containsString:@"Setup write completion unconfirmed"]);
        assert(![[interrupted reportText] containsString:@"No setup write was attempted"]);
    }
    // Opening and verifying the selected service are prerequisites, not writes.
    for (NSString *progress in @[@"opening", @"opened", @"verified"]) {
        for (NSString *stage in @[@"failed", @"closed", @"timeout"]) {
            TestController *unwritten = mock();
            unwritten.hostSetup = YES;
            if ([progress isEqualToString:@"verified"])
                [unwritten transportStage:@"opened" detail:@"Opened"];
            [unwritten transportStage:progress detail:@"Selected service check"];
            [unwritten transportStage:stage detail:@"Target could not be verified"];
            [unwritten transportStage:@"writing" detail:@"Late attempt callback"];
            [unwritten transportStage:@"sent" detail:@"Late completion callback"];
            assert(unwritten.ended && !unwritten.sent && !unwritten.writeAttempted);
            assert([unwritten.status.stringValue containsString:@"No setup write was attempted"]);
            assert([unwritten.status.stringValue componentsSeparatedByString:@"No setup write was attempted"].count == 2);
            assert([[unwritten reportText] containsString:@"No setup write was attempted"]);
            assert(![[unwritten reportText] containsString:@"completion unconfirmed"]);
            assert(![[unwritten reportText] containsString:@"Late"]);
        }
    }
    TestController *closed = mock();
    closed.hostSetup = YES;
    [closed transportStage:@"opened" detail:@"Opened"];
    [closed transportStage:@"verified" detail:@"Selected Samsung service verified"];
    [closed windowWillClose:[NSNotification notificationWithName:NSWindowWillCloseNotification object:nil]];
    [closed transportStage:@"sent" detail:@"Late callback"];
    assert(closed.ended && !closed.sent && ![[closed reportText] containsString:@"Late callback"]);
    assert([[closed reportText] containsString:@"No setup write was attempted"]);
    assert([[closed reportText] containsString:@"Samsung control service verified: yes"]);
    TestController *unverified = mock();
    unverified.hostSetup = YES;
    [unverified transportStage:@"failed" detail:@"Selected service did not match"];
    [unverified transportStage:@"verified" detail:@"Late verification"];
    assert(!unverified.controlServiceVerified && ![[unverified reportText] containsString:@"Late verification"]);
    TestController *listen = mock();
    listen.attempted = NO;
    [listen start:nil];
    assert(listen.attempted && listenAttempts == 1 && setupAttempts == 1);
    assert(![[listen reportText] containsString:@"Samsung control service verified:"]);
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
    [ok transportStage:@"opening" detail:@"Opening the selected service"];
    assert(!ok.ended && !ok.opened && !ok.continued.enabled && ok.stopped.enabled);
    [ok transportStage:@"opened" detail:@"opened"];
    assert(ok.opened && !ok.continued.enabled);
    assert(![[ok reportText] containsString:@"Samsung control service verified:"]);
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
    TestModeSelection();
    TestHostSetup();
    puts("UI state fixtures passed");
} return 0; }
