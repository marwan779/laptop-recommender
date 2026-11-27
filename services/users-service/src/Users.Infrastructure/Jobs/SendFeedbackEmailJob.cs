using Hangfire;
using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces.Email;
using Users.Application.Common.Interfaces.Jobs;
using Users.Application.Features.Notifications.Email;

namespace Users.Infrastructure.Jobs;

public sealed class SendFeedbackEmailJob(
    IEmailSender emailSender,
    ILogger<SendFeedbackEmailJob> logger)
{
    [AutomaticRetry(Attempts = 5)]
    public async Task ExecuteAdminAlertAsync(
        FeedbackAdminAlertEmailPayload payload,
        CancellationToken cancellationToken = default)
    {
        var subject = EmailBodyBuilder.BuildFeedbackAdminAlertSubject(payload);
        var htmlBody = EmailBodyBuilder.BuildFeedbackAdminAlertHtml(payload);

        await emailSender.SendAsync(
            new EmailMessage(payload.ToEmail, payload.AdminName, subject, htmlBody, payload.Description),
            cancellationToken);

        logger.LogInformation(
            "Sent feedback admin alert email [to={ToEmail}, reportId={ReportId}]",
            payload.ToEmail,
            payload.ReportId);
    }

    [AutomaticRetry(Attempts = 5)]
    public async Task ExecuteReviewedAsync(
        FeedbackReviewedEmailPayload payload,
        CancellationToken cancellationToken = default)
    {
        var subject = EmailBodyBuilder.BuildFeedbackReviewedSubject(payload);
        var htmlBody = EmailBodyBuilder.BuildFeedbackReviewedHtml(payload);

        await emailSender.SendAsync(
            new EmailMessage(payload.ToEmail, payload.RecipientName, subject, htmlBody, payload.AdminNotes),
            cancellationToken);

        logger.LogInformation(
            "Sent feedback reviewed email [to={ToEmail}, reportId={ReportId}, status={Status}]",
            payload.ToEmail,
            payload.ReportId,
            payload.Status);
    }
}
