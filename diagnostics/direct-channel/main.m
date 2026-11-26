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
@property (nonatomic, strong) NSTextField *status;
@property (nonatomic, strong) NSButton *startButton;
@property (nonatomic, strong) NSButton *continued;
@property (nonatomic, strong) NSButton *stopped;
@property (nonatomic, strong) NSButton *unsure;
@property (nonatomic, strong) NSButton *reportButton;
@property (nonatomic, strong) DirectTransport *transport;
@property (nonatomic, strong) NSMutableArray<NSString *> *events;
@property (nonatomic, strong) NSTimer *listeningTimer;
@property (nonatomic) NSTimeInterval startTime;
@property (nonatomic) NSTimeInterval openedTime;
@property (nonatomic) BOOL attempted;
@property (nonatomic) BOOL opened;
@property (nonatomic) BOOL ended;
@property (nonatomic) BOOL reported;
@end

@implementation ProbeController

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.events = [NSMutableArray array];
    self.transport = [[DirectTransport alloc] init];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 580, 410)
                                              styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                                                        NSWindowStyleMaskMiniaturizable
                                                backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"Buds On Connection Check";
    self.window.delegate = self;
    self.window.releasedWhenClosed = NO;

    NSTextField *title = label(@"Can the Fold keep playing?", 23, NSFontWeightSemibold);
    NSTextField *setup = label(@"Quit Galaxy Buds Manager, including its menu bar icon. Start with the Buds disconnected from the Mac and music from the Fold audible through the Buds.", 14, NSFontWeightRegular);
    NSTextField *explanation = label(@"This test opens the Buds’ Samsung control channel once. Opening it may interrupt the music. Listen for a few seconds, then choose what you heard.", 14, NSFontWeightRegular);
    self.startButton = [NSButton buttonWithTitle:@"Test while Fold music is playing" target:self action:@selector(start:)];
    self.status = label(@"Ready when you can hear the Fold.", 14, NSFontWeightMedium);
    self.continued = [NSButton buttonWithTitle:@"Music kept playing" target:self action:@selector(record:)];
    self.stopped = [NSButton buttonWithTitle:@"Music stopped" target:self action:@selector(record:)];
    self.unsure = [NSButton buttonWithTitle:@"Unsure" target:self action:@selector(record:)];
    NSStackView *choices = [NSStackView stackViewWithViews:@[self.continued, self.stopped, self.unsure]];
    choices.spacing = 8;
    self.reportButton = [NSButton buttonWithTitle:@"Copy test report" target:self action:@selector(copyReport:)];
    self.reportButton.enabled = NO;

    NSStackView *stack = [NSStackView stackViewWithViews:@[title, setup, explanation, self.startButton,
                                                            self.status, choices, self.reportButton]];
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
    for (NSTextField *field in @[title, setup, explanation, self.status]) {
        [field.widthAnchor constraintEqualToAnchor:stack.widthAnchor].active = YES;
    }
    [self updateChoices];

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

- (void)updateChoices {
    BOOL canRecord = self.attempted && !self.reported;
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

- (void)start:(id)sender {
    if (self.attempted) return;
    self.startTime = NSProcessInfo.processInfo.systemUptime;
    [self.events removeAllObjects];
    NSString *blocked = nil;
    if ([NSRunningApplication runningApplicationsWithBundleIdentifier:ManagerBundleID].count) {
        blocked = @"Galaxy Buds Manager is still running. Quit it from its menu bar icon, then try again.";
    } else {
        blocked = [self.transport preflight];
    }
    if (blocked) {
        self.status.stringValue = blocked;
        [self addEvent:[@"Preflight stopped. " stringByAppendingString:blocked]];
        return;
    }

    self.attempted = YES;
    self.startButton.enabled = NO;
    [self addEvent:@"Listener started the test with Fold music audible."];
    self.status.stringValue = @"Opening the Samsung control channel. Keep listening.";
    [self updateChoices];
    __weak ProbeController *weakSelf = self;
    [self.transport start:^(NSString *stage, NSString *detail) {
        [weakSelf transportStage:stage detail:detail];
    }];
}

- (void)transportStage:(NSString *)stage detail:(NSString *)detail {
    if (self.ended) return;
    [self addEvent:[NSString stringWithFormat:@"Transport %@. %@", stage, detail ?: @""]];
    if ([stage isEqualToString:@"opened"]) {
        if (self.opened) return;
        self.opened = YES;
        self.openedTime = NSProcessInfo.processInfo.systemUptime;
        self.status.stringValue = @"The channel opened. Listen for a few seconds, then choose what you heard.";
        __weak ProbeController *weakSelf = self;
        self.listeningTimer = [NSTimer scheduledTimerWithTimeInterval:0.25 repeats:YES block:^(NSTimer *timer) {
            (void)timer;
            [weakSelf tick];
        }];
    } else if ([stage isEqualToString:@"closed"] || [stage isEqualToString:@"failed"] ||
               [stage isEqualToString:@"timeout"]) {
        self.ended = YES;
        [self stopObservationTimer];
        self.status.stringValue = [NSString stringWithFormat:@"%@ Choose what you heard during the attempt.", detail];
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
    if (self.reported || !self.attempted || !button.enabled) return;
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

- (void)copyReport:(id)sender {
    NSString *body = [self.events componentsJoinedByString:@"\n"];
    NSString *report = [NSString stringWithFormat:@"Buds On Connection Check 1.0\nChannel opened: %@\n%@\n%@",
                        self.opened ? @"yes" : @"unconfirmed", body,
                        self.reported ? @"Listener observation recorded." : (self.attempted ? @"Listener observation pending." : @"No opening attempt was made.")];
    NSPasteboard *pasteboard = NSPasteboard.generalPasteboard;
    [pasteboard clearContents];
    [pasteboard setString:report forType:NSPasteboardTypeString];
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
