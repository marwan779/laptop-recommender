using System.Globalization;
using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Messaging;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Features.Notifications.Events;
using Users.Domain.Entities;

namespace Users.Application.Features.Notifications.Handlers;

/// <summary>
/// Matches incoming laptop price/stock change events against active wishlist subscriptions
/// and persists user notifications within the consumer's atomic unit of work.
/// </summary>
public sealed class LaptopPriceChangedHandler(
    IWishlistRepository wishlistRepository,
    INotificationRepository notificationRepository,
    IDateTimeProvider dateTimeProvider,
    ILogger<LaptopPriceChangedHandler> logger) : IIntegrationEventHandler<LaptopPriceChangedEvent>
{
    public async Task HandleAsync(
        LaptopPriceChangedEvent integrationEvent,
        string messageId,
        CancellationToken cancellationToken = default)
    {
        var subscribers = await wishlistRepository.GetSubscribersByCanonicalIdAsync(
            integrationEvent.CanonicalId,
            cancellationToken);

        if (subscribers.Count == 0)
        {
            logger.LogInformation(
                "No active wishlist subscribers for LaptopPriceChangedEvent [messageId={MessageId}, canonicalId={CanonicalId}]",
                messageId,
                integrationEvent.CanonicalId);
            return;
        }

        var normalizedChangeType = NormalizeChangeType(integrationEvent);
        var utcNow = dateTimeProvider.UtcNow;
        var notifications = new List<Notification>();

        foreach (var item in subscribers)
        {
            if (!ShouldNotify(item, integrationEvent, normalizedChangeType))
            {
                continue;
            }

            var (title, message) = BuildNotificationCopy(integrationEvent, normalizedChangeType);
            notifications.Add(Notification.Create(
                item.UserId,
                integrationEvent.CanonicalId,
                title,
                message,
                normalizedChangeType,
                integrationEvent.OldPriceEgp,
                integrationEvent.NewPriceEgp,
                integrationEvent.CheapestStore));

            item.RecordNotificationSent(integrationEvent.NewPriceEgp, utcNow);
        }

        if (notifications.Count > 0)
        {
            await notificationRepository.AddRangeAsync(notifications, cancellationToken);
        }

        logger.LogInformation(
            "Processed LaptopPriceChangedEvent [messageId={MessageId}, canonicalId={CanonicalId}, changeType={ChangeType}, subscribers={SubscriberCount}, notificationsCreated={NotificationCount}]",
            messageId,
            integrationEvent.CanonicalId,
            normalizedChangeType,
            subscribers.Count,
            notifications.Count);
    }

    private static string NormalizeChangeType(LaptopPriceChangedEvent evt)
    {
        var raw = (evt.ChangeType ?? string.Empty).Trim().ToUpperInvariant();
        if (!string.IsNullOrEmpty(raw))
        {
            return raw;
        }

        if (evt.OldPriceEgp is > 0 && evt.NewPriceEgp is > 0)
        {
            return evt.NewPriceEgp < evt.OldPriceEgp ? "PRICE_DROP" : "PRICE_CHANGE";
        }

        return evt.InStock ? "RESTOCK" : "PRICE_CHANGE";
    }

    private static bool ShouldNotify(
        WishlistItem item,
        LaptopPriceChangedEvent evt,
        string changeType)
    {
        var isRestock = evt.InStock && changeType is "RESTOCK" or "BACK_IN_STOCK";
        var isPriceDrop = changeType == "PRICE_DROP"
            || (evt.OldPriceEgp is > 0 && evt.NewPriceEgp is > 0 && evt.NewPriceEgp < evt.OldPriceEgp);
        var isPriceChanged = evt.OldPriceEgp != evt.NewPriceEgp;

        if (item.NotifyOnAnyChange && (isPriceDrop || isRestock || isPriceChanged))
        {
            return true;
        }

        if (isRestock && item.NotifyOnRestock)
        {
            return true;
        }

        if (isPriceDrop && item.NotifyOnPriceDrop)
        {
            if (item.TargetPriceEgp.HasValue)
            {
                return evt.NewPriceEgp.HasValue && evt.NewPriceEgp.Value <= item.TargetPriceEgp.Value;
            }

            return true;
        }

        return false;
    }

    private static (string Title, string Message) BuildNotificationCopy(
        LaptopPriceChangedEvent evt,
        string changeType)
    {
        var laptopTitle = string.IsNullOrWhiteSpace(evt.Title) ? evt.CanonicalId : evt.Title.Trim();
        var storeSuffix = string.IsNullOrWhiteSpace(evt.CheapestStore)
            ? string.Empty
            : $" at {evt.CheapestStore.Trim()}";

        if (changeType is "RESTOCK" or "BACK_IN_STOCK")
        {
            var priceText = evt.NewPriceEgp.HasValue
                ? $" at {FormatPrice(evt.NewPriceEgp.Value)}"
                : string.Empty;

            return (
                $"Back in stock: {laptopTitle}",
                $"{laptopTitle} is back in stock{priceText}{storeSuffix}.");
        }

        if (changeType == "PRICE_DROP" && evt.OldPriceEgp.HasValue && evt.NewPriceEgp.HasValue)
        {
            return (
                $"Price drop: {laptopTitle}",
                $"{laptopTitle} dropped from {FormatPrice(evt.OldPriceEgp.Value)} to {FormatPrice(evt.NewPriceEgp.Value)}{storeSuffix}.");
        }

        if (evt.NewPriceEgp.HasValue)
        {
            return (
                $"Price update: {laptopTitle}",
                $"{laptopTitle} is now {FormatPrice(evt.NewPriceEgp.Value)}{storeSuffix}.");
        }

        return (
            $"Update: {laptopTitle}",
            $"{laptopTitle} has a status update{storeSuffix}.");
    }

    private static string FormatPrice(decimal amount)
        => string.Format(CultureInfo.InvariantCulture, "{0:N0} EGP", amount);
}
