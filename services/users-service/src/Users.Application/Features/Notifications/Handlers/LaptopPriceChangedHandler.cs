using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces.Messaging;
using Users.Application.Features.Notifications.Events;

namespace Users.Application.Features.Notifications.Handlers;

/// <summary>
/// Mock integration event handler for laptop price/stock transitions.
/// Logs receipt only; wishlist matching and notification dispatch will be wired in a later step.
/// </summary>
public sealed class LaptopPriceChangedHandler(
    ILogger<LaptopPriceChangedHandler> logger) : IIntegrationEventHandler<LaptopPriceChangedEvent>
{
    public Task HandleAsync(
        LaptopPriceChangedEvent integrationEvent,
        string messageId,
        CancellationToken cancellationToken = default)
    {
        logger.LogInformation(
            "Received mock LaptopPriceChangedEvent [messageId={MessageId}, canonicalId={CanonicalId}, changeType={ChangeType}, oldPrice={OldPriceEgp}, newPrice={NewPriceEgp}, store={CheapestStore}, inStock={InStock}]",
            messageId,
            integrationEvent.CanonicalId,
            integrationEvent.ChangeType,
            integrationEvent.OldPriceEgp,
            integrationEvent.NewPriceEgp,
            integrationEvent.CheapestStore,
            integrationEvent.InStock);

        return Task.CompletedTask;
    }
}
