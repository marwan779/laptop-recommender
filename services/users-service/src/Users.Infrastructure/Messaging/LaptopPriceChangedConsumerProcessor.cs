using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Logging;
using Users.Application.Common.Interfaces.Messaging;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Features.Notifications.Events;
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

        LaptopPriceChangedEvent? integrationEvent;
        try
        {
            integrationEvent = JsonSerializer.Deserialize<LaptopPriceChangedEvent>(payloadJson, SnakeCaseJsonOptions);
        }
        catch (JsonException ex)
        {
            logger.LogError(ex, "Malformed JSON payload for message [messageId={MessageId}]", messageId);
            return MessageProcessOutcome.DeadLetter;
        }

        if (integrationEvent is null || string.IsNullOrWhiteSpace(integrationEvent.CanonicalId))
        {
            logger.LogWarning("Invalid LaptopPriceChangedEvent payload [messageId={MessageId}]", messageId);
            return MessageProcessOutcome.DeadLetter;
        }

        using var scope = scopeFactory.CreateScope();
        var inboxRepo = scope.ServiceProvider.GetRequiredService<IInboxRepository>();
        var handler = scope.ServiceProvider.GetRequiredService<IIntegrationEventHandler<LaptopPriceChangedEvent>>();
        var dateTimeProvider = scope.ServiceProvider.GetRequiredService<IDateTimeProvider>();
        var unitOfWork = scope.ServiceProvider.GetRequiredService<IUnitOfWork>();

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

        return MessageProcessOutcome.Ack;
    }
}
