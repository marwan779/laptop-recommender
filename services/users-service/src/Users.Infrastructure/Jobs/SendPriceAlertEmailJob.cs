using Hangfire;
using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces.Email;
using Users.Application.Common.Interfaces.Jobs;
using Users.Application.Features.Notifications.Email;

namespace Users.Infrastructure.Jobs;

public sealed class SendPriceAlertEmailJob(
    IEmailSender emailSender,
    ILogger<SendPriceAlertEmailJob> logger)
{
    [AutomaticRetry(Attempts = 5)]
    public async Task ExecuteAsync(PriceAlertEmailJobPayload payload, CancellationToken cancellationToken = default)
    {
        var subject = EmailBodyBuilder.BuildPriceAlertSubject(payload);
        var htmlBody = EmailBodyBuilder.BuildPriceAlertHtml(payload);
        var plainTextBody = EmailBodyBuilder.BuildPriceAlertPlainText(payload);

        var message = new EmailMessage(
            payload.ToEmail,
            payload.FullName,
            subject,
            htmlBody,
            plainTextBody);

        await emailSender.SendAsync(message, cancellationToken);

        logger.LogInformation(
            "Completed background price alert email job [to={ToEmail}, canonicalId={CanonicalId}, changeType={ChangeType}]",
            payload.ToEmail,
            payload.CanonicalId,
            payload.ChangeType);
    }
}
