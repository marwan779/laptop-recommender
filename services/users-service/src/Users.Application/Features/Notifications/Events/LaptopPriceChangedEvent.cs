namespace Users.Application.Features.Notifications.Events;

public sealed record LaptopPriceChangedEvent(
    string CanonicalId,
    string Title,
    decimal? OldPriceEgp,
    decimal? NewPriceEgp,
    string CheapestStore,
    bool InStock,
    string ChangeType);

public sealed record LaptopPriceChangedBatchPayload(
    string BatchId,
    string? StoreKey,
    IReadOnlyList<LaptopPriceChangedEvent> Changes);

public sealed record LaptopPriceChangedBatchEvent(
    string EventId,
    string EventType,
    string? Timestamp,
    string? CorrelationId,
    LaptopPriceChangedBatchPayload Payload);
