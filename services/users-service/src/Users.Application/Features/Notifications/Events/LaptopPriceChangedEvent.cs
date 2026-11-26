namespace Users.Application.Features.Notifications.Events;

public sealed record LaptopPriceChangedEvent(
    string CanonicalId,
    string Title,
    decimal? OldPriceEgp,
    decimal? NewPriceEgp,
    string CheapestStore,
    bool InStock,
    string ChangeType);
