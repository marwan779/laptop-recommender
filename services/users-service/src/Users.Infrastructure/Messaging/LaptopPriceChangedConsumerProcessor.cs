using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Jobs;
using Users.Application.Common.Interfaces.Logging;
using Users.Application.Common.Interfaces.Messaging;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Features.Notifications.Events;
using Users.Application.Features.Notifications.Services;
using Users.Domain.Entities;

namespace Users.Infrastructure.Messaging;

public enum MessageProcessOutcome
{
    Ack = 0,
    DeadLetter = 1,
    Retry = 2,
}

public sealed class LaptopPriceChangedConsumerProcessor(
    IServiceScopeFactory scopeFactory,
    ILogContextAccessor logContextAccessor,
    ILogger<LaptopPriceChangedConsumerProcessor> logger)
{
    private static readonly JsonSerializerOptions SnakeCaseJsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public async Task<MessageProcessOutcome> ProcessAsync(
        string messageId,
        string routingKey,
        string payloadJson,
        string? correlationId,
        CancellationToken cancellationToken = default)
    {
        using var logScope = logContextAccessor.BeginScope(correlationId);

        if (string.IsNullOrWhiteSpace(messageId))
        {
            logger.LogWarning("Rejected RabbitMQ message with empty message_id [routingKey={RoutingKey}]", routingKey);
            return MessageProcessOutcome.DeadLetter;
        }

        LaptopPriceChangedBatchEvent? integrationEvent;
        try
        {
            integrationEvent = JsonSerializer.Deserialize<LaptopPriceChangedBatchEvent>(payloadJson, SnakeCaseJsonOptions);
        }
        catch (JsonException ex)
        {
            logger.LogError(ex, "Malformed JSON payload for message [messageId={MessageId}]", messageId);
            return MessageProcessOutcome.DeadLetter;
        }

        if (integrationEvent?.Payload?.Changes is null
            || integrationEvent.Payload.Changes.Count == 0
            || integrationEvent.Payload.Changes.Any(c => string.IsNullOrWhiteSpace(c.CanonicalId)))
        {
            logger.LogWarning("Invalid LaptopPriceChangedBatchEvent payload [messageId={MessageId}]", messageId);
            return MessageProcessOutcome.DeadLetter;
        }

        using var scope = scopeFactory.CreateScope();
        var inboxRepo = scope.ServiceProvider.GetRequiredService<IInboxRepository>();
        var handler = scope.ServiceProvider.GetRequiredService<IIntegrationEventHandler<LaptopPriceChangedBatchEvent>>();
        var dateTimeProvider = scope.ServiceProvider.GetRequiredService<IDateTimeProvider>();
        var unitOfWork = scope.ServiceProvider.GetRequiredService<IUnitOfWork>();
        var affectedUserTracker = scope.ServiceProvider.GetRequiredService<AffectedUserTracker>();
        var cacheProvider = scope.ServiceProvider.GetRequiredService<ICacheProvider>();
        var jobScheduler = scope.ServiceProvider.GetService<IBackgroundJobScheduler>();

        if (await inboxRepo.ExistsAsync(messageId, cancellationToken))
        {
            logger.LogInformation(
                "Skipping duplicate RabbitMQ message [messageId={MessageId}, routingKey={RoutingKey}]",
                messageId,
                routingKey);
            return MessageProcessOutcome.Ack;
        }

        await handler.HandleAsync(integrationEvent, messageId, cancellationToken);

        var inboxEntry = InboxMessage.Create(messageId, routingKey, dateTimeProvider.UtcNow);
        await inboxRepo.AddAsync(inboxEntry, cancellationToken);
        await unitOfWork.SaveChangesAsync(cancellationToken);

        await InvalidateAffectedUserCachesAsync(affectedUserTracker, cacheProvider, cancellationToken);
        EnqueuePriceAlertEmails(affectedUserTracker, jobScheduler);

        return MessageProcessOutcome.Ack;
    }

    private void EnqueuePriceAlertEmails(
        AffectedUserTracker affectedUserTracker,
        IBackgroundJobScheduler? jobScheduler)
    {
        if (jobScheduler is null)
        {
            return;
        }

        foreach (var emailPayload in affectedUserTracker.SnapshotEmailAlerts())
        {
            try
            {
                jobScheduler.EnqueuePriceAlertEmail(emailPayload);
            }
            catch (Exception ex)
            {
                logger.LogWarning(
                    ex,
                    "Failed to enqueue price alert email job after commit [to={ToEmail}, canonicalId={CanonicalId}]",
                    emailPayload.ToEmail,
                    emailPayload.CanonicalId);
            }
        }
    }

    private async Task InvalidateAffectedUserCachesAsync(
        AffectedUserTracker affectedUserTracker,
        ICacheProvider cacheProvider,
        CancellationToken cancellationToken)
    {
        foreach (var userId in affectedUserTracker.Snapshot())
        {
            try
            {
                await cacheProvider.ClearPrefixAsync($"users:{userId}:notifications:", cancellationToken);
                await cacheProvider.ClearPrefixAsync($"users:{userId}:wishlist:", cancellationToken);
            }
            catch (Exception ex)
            {
                // The message is already committed; cache invalidation must never
                // cause a redelivery or dead-letter.
                logger.LogWarning(
                    ex,
                    "Failed to invalidate cache after price-change commit [userId={UserId}]",
                    userId);
            }
        }
    }
}
