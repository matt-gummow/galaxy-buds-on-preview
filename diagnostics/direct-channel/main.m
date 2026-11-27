#import <AppKit/AppKit.h>
#import "DirectTransport.h"

static NSString *const ManagerBundleID = @"me.timschneeberger.galaxybudsclient";

static NSTextField *label(NSString *text, CGFloat size, NSFontWeight weight) {
    NSTextField *field = [NSTextField wrappingLabelWithString:text];
    field.font = [NSFont systemFontOfSize:size weight:weight];
    field.selectable = YES;
    return field;
}

@interface ProbeController : NSObject <NSApplicationDelegate, NSWindowDelegate>
@property (nonatomic, strong) NSWindow *window;
@property (nonatomic, strong) NSSegmentedControl *mode;
@property (nonatomic, strong) NSTextField *instructions;
@property (nonatomic, strong) NSStackView *choices;
@property (nonatomic, strong) NSTextField *status;
@property (nonatomic, strong) NSButton *startButton;
@property (nonatomic, strong) NSButton *continued;
@property (nonatomic, strong) NSButton *stopped;
@property (nonatomic, strong) NSButton *unsure;
@property (nonatomic, strong) NSButton *reportButton;
@property (nonatomic, strong) DirectTransport *transport;
@property (nonatomic, strong) NSMutableArray<NSString *> *events;
@property (nonatomic, strong) NSTimer *listeningTimer;
@property (nonatomic, strong) NSDate *startDate;
@property (nonatomic) NSTimeInterval startTime;
@property (nonatomic) NSTimeInterval openedTime;
@property (nonatomic) BOOL attempted;
@property (nonatomic) BOOL opened;
@property (nonatomic) BOOL ended;
@property (nonatomic) BOOL reported;
@property (nonatomic) BOOL hostSetup;
@property (nonatomic) BOOL writeAttempted;
@property (nonatomic) BOOL sent;
@end

@implementation ProbeController

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.events = [NSMutableArray array];
    self.transport = [[DirectTransport alloc] init];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 580, 410)
                                              styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                                                        NSWindowStyleMaskMiniaturizable
                                                backing:NSBackingStoreBuffered defer:NO];
    self.window.title = [NSString stringWithFormat:@"Buds On Connection Check %@",
                         [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"]];
    self.window.delegate = self;
    self.window.releasedWhenClosed = NO;

    self.mode = [NSSegmentedControl segmentedControlWithLabels:@[@"Fold playback", @"Mac host setup"]
                                                   trackingMode:NSSegmentSwitchTrackingSelectOne
                                                         target:self action:@selector(selectMode:)];
    self.mode.selectedSegment = 0;
    self.instructions = label(@"", 14, NSFontWeightRegular);
    self.startButton = [NSButton buttonWithTitle:@"" target:self action:@selector(start:)];
    self.status = label(@"", 14, NSFontWeightMedium);
    self.continued = [NSButton buttonWithTitle:@"Music kept playing" target:self action:@selector(record:)];
    self.stopped = [NSButton buttonWithTitle:@"Music stopped" target:self action:@selector(record:)];
    self.unsure = [NSButton buttonWithTitle:@"Unsure" target:self action:@selector(record:)];
    self.choices = [NSStackView stackViewWithViews:@[self.continued, self.stopped, self.unsure]];
    self.choices.spacing = 8;
    self.reportButton = [NSButton buttonWithTitle:@"Copy test report" target:self action:@selector(copyReport:)];
    self.reportButton.enabled = NO;

    NSStackView *stack = [NSStackView stackViewWithViews:@[self.mode, self.instructions, self.startButton,
                                                          self.status, self.choices, self.reportButton]];
    stack.orientation = NSUserInterfaceLayoutOrientationVertical;
    stack.alignment = NSLayoutAttributeLeading;
    stack.spacing = 13;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    NSView *content = self.window.contentView;
    [content addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
        [stack.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:24],
        [stack.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-24],
        [stack.topAnchor constraintEqualToAnchor:content.topAnchor constant:24],
        [stack.bottomAnchor constraintLessThanOrEqualToAnchor:content.bottomAnchor constant:-16]
    ]];
    for (NSTextField *field in @[self.instructions, self.status]) {
        [field.widthAnchor constraintEqualToAnchor:stack.widthAnchor].active = YES;
    }
    [self selectMode:self.mode];

    NSMenu *menu = [[NSMenu alloc] init];
    NSMenuItem *appItem = [[NSMenuItem alloc] init];
    [menu addItem:appItem];
    NSMenu *appMenu = [[NSMenu alloc] init];
    [appMenu addItemWithTitle:@"Quit Buds On Connection Check" action:@selector(terminate:) keyEquivalent:@"q"];
    appItem.submenu = appMenu;
    NSApp.mainMenu = menu;
    [self.window center];
    [self.window makeKeyAndOrderFront:nil];
    if (@available(macOS 14.0, *)) [NSApp activate];
}

- (void)selectMode:(NSSegmentedControl *)mode {
    if (self.attempted) return;
    self.hostSetup = mode.selectedSegment == 1;
    self.instructions.stringValue = self.hostSetup
        ? @"Connect the Buds to this Mac, quit Galaxy Buds Manager from its menu bar icon, and leave the Buds out of their case. This experiment sends one host setup message observed on a Galaxy Book."
        : @"Quit Galaxy Buds Manager from its menu bar icon. Leave the Buds disconnected from the Mac and play music from the Fold through the Buds. Opening the control channel may interrupt playback.";
    self.startButton.title = self.hostSetup ? @"Set up this Mac…" : @"Test while Fold music is playing";
    self.status.stringValue = self.hostSetup ? @"Ready when the Buds are connected to the Mac." : @"Ready when you can hear the Fold.";
    self.choices.hidden = self.hostSetup;
    [self.events removeAllObjects];
    self.reportButton.enabled = NO;
    self.reportButton.title = @"Copy test report";
    [self updateChoices];
}

- (void)updateChoices {
    BOOL canRecord = !self.hostSetup && self.attempted && !self.reported;
    self.stopped.enabled = canRecord;
    self.unsure.enabled = canRecord;
    self.continued.enabled = canRecord && (self.ended ||
        (self.opened && NSProcessInfo.processInfo.systemUptime - self.openedTime >= 3.0));
}

- (void)addEvent:(NSString *)text {
    NSTimeInterval elapsed = NSProcessInfo.processInfo.systemUptime - self.startTime;
    [self.events addObject:[NSString stringWithFormat:@"+%.1fs  %@", elapsed, text]];
    self.reportButton.enabled = YES;
    self.reportButton.title = @"Copy test report";
}

- (BOOL)confirmHostSetup {
    NSAlert *alert = [NSAlert new];
    alert.messageText = @"Send the Galaxy Book host setup message once?";
    alert.informativeText = @"This writes the Book’s version 3 host setting to your Buds On and may interrupt audio. Afterward, you can check whether the Fold and Mac stay connected.";
    [alert addButtonWithTitle:@"Cancel"];
    [alert addButtonWithTitle:@"Send once"];
    return [alert runModal] == NSAlertSecondButtonReturn;
}

- (NSString *)preflightBlocker {
    if ([NSRunningApplication runningApplicationsWithBundleIdentifier:ManagerBundleID].count)
        return @"Galaxy Buds Manager is still running. Quit it from its menu bar icon, then try again.";
    return [self.transport preflight];
}

- (void)start:(id)sender {
    if (self.attempted || (self.hostSetup && ![self confirmHostSetup])) return;
    self.startDate = [NSDate date];
    self.startTime = NSProcessInfo.processInfo.systemUptime;
    [self.events removeAllObjects];
    NSString *blocked = [self preflightBlocker];
    if (blocked) {
        self.status.stringValue = self.hostSetup
            ? [blocked stringByAppendingString:@" No setup write was attempted."] : blocked;
        [self addEvent:[@"Preflight stopped. " stringByAppendingString:blocked]];
        return;
    }

    self.attempted = YES;
    self.mode.enabled = NO;
    self.startButton.enabled = NO;
    [self addEvent:self.hostSetup ? @"User confirmed one Galaxy Book host setup write."
                                 : @"Listener started the test with Fold music audible."];
    self.status.stringValue = self.hostSetup ? @"Opening the control channel for host setup…"
                                            : @"Opening the Samsung control channel. Keep listening.";
    [self updateChoices];
    __weak ProbeController *weakSelf = self;
    void (^onEvent)(NSString *, NSString *) = ^(NSString *stage, NSString *detail) {
        [weakSelf transportStage:stage detail:detail];
    };
    if (self.hostSetup) [self.transport startBookHostSetup:onEvent];
    else [self.transport start:onEvent];
}

- (void)transportStage:(NSString *)stage detail:(NSString *)detail {
    if (self.ended) return;
    [self addEvent:[NSString stringWithFormat:@"Transport %@. %@", stage, detail ?: @""]];
    if ([stage isEqualToString:@"discovering"]) {
        self.status.stringValue = self.hostSetup
            ? @"Checking the Buds’ Samsung control service. No setup write has been attempted."
            : @"Checking the Buds’ Samsung control service. Keep listening.";
    } else if ([stage isEqualToString:@"opened"]) {
        if (self.opened) return;
        self.opened = YES;
        self.openedTime = NSProcessInfo.processInfo.systemUptime;
        if (self.hostSetup) {
            self.status.stringValue = @"Channel open. No setup write has been attempted.";
            return;
        }
        self.status.stringValue = @"The channel opened. Listen for a few seconds, then choose what you heard.";
        __weak ProbeController *weakSelf = self;
        self.listeningTimer = [NSTimer scheduledTimerWithTimeInterval:0.25 repeats:YES block:^(NSTimer *timer) {
            (void)timer;
            [weakSelf tick];
        }];
    } else if (self.hostSetup && [stage isEqualToString:@"writing"]) {
        self.writeAttempted = YES;
        self.status.stringValue = @"The Mac attempted one setup write. Waiting for local completion…";
    } else if (self.hostSetup && [stage isEqualToString:@"sent"]) {
        self.writeAttempted = YES;
        self.sent = YES;
        self.ended = YES;
        [self.transport stop];
        self.status.stringValue = @"The Mac completed the setup write. Earbud acceptance is unverified. With the Mac connected, reconnect the Fold once. Check whether both stay connected, then try Mac music, a Fold call, and music after hang-up. Copy the report and include what you heard.";
    } else if ([stage isEqualToString:@"closed"] || [stage isEqualToString:@"failed"] ||
               [stage isEqualToString:@"timeout"]) {
        self.ended = YES;
        [self stopObservationTimer];
        self.status.stringValue = self.hostSetup
            ? [NSString stringWithFormat:@"%@ %@ Copy the test report.", detail ?: @"The attempt ended.",
               self.writeAttempted ? @"Setup write completion unconfirmed."
                                   : @"No setup write was attempted."]
            : [NSString stringWithFormat:@"%@ Choose what you heard during the attempt.", detail];
        // Terminal transport events own their channel cleanup.
    }
    [self updateChoices];
}

- (void)tick {
    if (self.ended) return;
    if (NSProcessInfo.processInfo.systemUptime - self.openedTime >= 15.0) {
        self.ended = YES;
        [self stopObservationTimer];
        [self.transport stop];
        [self addEvent:@"Observation window ended after 15 seconds. Probe closed its channel."];
        self.status.stringValue = @"The test window ended and the probe closed its channel. Choose what you heard while it was open.";
    }
    [self updateChoices];
}

- (void)stopObservationTimer {
    [self.listeningTimer invalidate];
    self.listeningTimer = nil;
}

- (void)record:(NSButton *)button {
    if (self.hostSetup || self.reported || !self.attempted || !button.enabled) return;
    self.reported = YES;
    self.ended = YES;
    [self stopObservationTimer];
    [self.transport stop];
    [self addEvent:[NSString stringWithFormat:@"Listener reported: %@.", button.title]];
    self.status.stringValue = [NSString stringWithFormat:@"%@. %@. You can copy the report.",
                              self.opened ? @"Channel opened" : @"Channel opening was unconfirmed",
                              button.title];
    [self updateChoices];
}

- (NSString *)reportText {
    NSString *body = [self.events componentsJoinedByString:@"\n"];
    NSString *result;
    if (!self.attempted) result = self.hostSetup
        ? @"No opening attempt was made. No setup write was attempted." : @"No opening attempt was made.";
    else if (self.hostSetup) {
        if (self.sent) result = @"Mac completed one setup write. Earbud acceptance and audio behavior remain unverified.";
        else if (!self.writeAttempted) result = self.ended
            ? @"No setup write was attempted." : @"No setup write has been attempted.";
        else result = @"Setup write completion unconfirmed.";
    } else result = self.reported ? @"Listener observation recorded." : @"Listener observation pending.";
    NSString *start = self.startDate ? [[NSISO8601DateFormatter new] stringFromDate:self.startDate] : @"Unknown";
    return [NSString stringWithFormat:@"Buds On Connection Check %@\nMode: %@\nStarted: %@\nChannel opened: %@\n%@\n%@",
            [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"],
            self.hostSetup ? @"Mac host setup" : @"Fold playback", start, self.opened ? @"yes" : @"unconfirmed", body, result];
}

- (void)copyReport:(id)sender {
    NSPasteboard *pasteboard = NSPasteboard.generalPasteboard;
    [pasteboard clearContents];
    [pasteboard setString:[self reportText] forType:NSPasteboardTypeString];
    self.reportButton.title = @"Report copied";
}

- (void)windowWillClose:(NSNotification *)notification {
    self.ended = YES;
    [self stopObservationTimer];
    [self.transport stop];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender { return YES; }

- (void)applicationWillTerminate:(NSNotification *)notification { [self windowWillClose:notification]; }

@end

int main(void) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        __attribute__((objc_precise_lifetime)) ProbeController *controller = [[ProbeController alloc] init];
        app.delegate = controller;
        [app run];
    }
    return 0;
}
