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

public interface IBackgroundJobScheduler
{
    string EnqueuePriceAlertEmail(PriceAlertEmailJobPayload payload);
}
