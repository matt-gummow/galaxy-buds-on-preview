#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Use on the main thread. Each instance makes at most one opening attempt.
@interface DirectTransport : NSObject
- (nullable NSString *)preflight;
- (void)start:(void (^)(NSString *stage, NSString *detail))event;
/// Explicit one-shot setup. "sent" reports local transport completion only.
- (void)startBookHostSetup:(void (^)(NSString *stage, NSString *detail))event;
- (void)stop;
@end

NS_ASSUME_NONNULL_END
