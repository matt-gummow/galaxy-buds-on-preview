#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Use on the main thread. Each instance makes at most one opening attempt.
@interface DirectTransport : NSObject
- (nullable NSString *)preflight;
- (void)start:(void (^)(NSString *stage, NSString *detail))event;
/// Explicit one-shot setup. "sent" reports local completion and leaves the channel open.
- (void)startBookHostSetup:(void (^)(NSString *stage, NSString *detail))event;
/// Passive snapshot of the RFCOMM channel and the selected peer's baseband link.
- (NSString *)connectionStatus;
- (void)stop;
@end

NS_ASSUME_NONNULL_END
