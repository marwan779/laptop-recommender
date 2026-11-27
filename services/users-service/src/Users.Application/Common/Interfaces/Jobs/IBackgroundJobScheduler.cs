namespace Users.Application.Common.Interfaces.Jobs;

public sealed record PriceAlertEmailJobPayload(
    string ToEmail,
    string FullName,
    string PreferredLanguage,
    string CanonicalId,
    string LaptopTitle,
    string ChangeType,
    decimal? OldPriceEgp,
    decimal? NewPriceEgp,
    string? CheapestStore,
    bool InStock);

public sealed record FeedbackAdminAlertEmailPayload(
    string ToEmail,
    string AdminName,
    Guid ReportId,
    string Category,
    string Title,
    string Description,
    string? ReporterEmail,
    string? LaptopTitleSnapshot);

public sealed record FeedbackReviewedEmailPayload(
    string ToEmail,
    string RecipientName,
    string PreferredLanguage,
    Guid ReportId,
    string Category,
    string Title,
    string Status,
    string? AdminNotes,
    string? LaptopTitleSnapshot);

public interface IBackgroundJobScheduler
{
    string EnqueuePriceAlertEmail(PriceAlertEmailJobPayload payload);
    string EnqueueFeedbackAdminAlertEmail(FeedbackAdminAlertEmailPayload payload);
    string EnqueueFeedbackReviewedEmail(FeedbackReviewedEmailPayload payload);
}
