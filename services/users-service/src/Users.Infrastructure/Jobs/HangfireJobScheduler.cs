using Hangfire;
using Users.Application.Common.Interfaces.Jobs;

namespace Users.Infrastructure.Jobs;

public sealed class HangfireJobScheduler(IBackgroundJobClient backgroundJobClient) : IBackgroundJobScheduler
{
    public string EnqueuePriceAlertEmail(PriceAlertEmailJobPayload payload)
        => backgroundJobClient.Enqueue<SendPriceAlertEmailJob>(
            job => job.ExecuteAsync(payload, CancellationToken.None));

    public string EnqueueFeedbackAdminAlertEmail(FeedbackAdminAlertEmailPayload payload)
        => backgroundJobClient.Enqueue<SendFeedbackEmailJob>(
            job => job.ExecuteAdminAlertAsync(payload, CancellationToken.None));

    public string EnqueueFeedbackReviewedEmail(FeedbackReviewedEmailPayload payload)
        => backgroundJobClient.Enqueue<SendFeedbackEmailJob>(
            job => job.ExecuteReviewedAsync(payload, CancellationToken.None));
}
