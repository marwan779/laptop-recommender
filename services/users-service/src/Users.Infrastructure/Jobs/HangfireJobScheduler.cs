using Hangfire;
using Users.Application.Common.Interfaces.Jobs;

namespace Users.Infrastructure.Jobs;

public sealed class HangfireJobScheduler(IBackgroundJobClient backgroundJobClient) : IBackgroundJobScheduler
{
    public string EnqueuePriceAlertEmail(PriceAlertEmailJobPayload payload)
        => backgroundJobClient.Enqueue<SendPriceAlertEmailJob>(
            job => job.ExecuteAsync(payload, CancellationToken.None));
}
