namespace Users.Application.Common.Interfaces.Messaging;

public interface IIntegrationEventHandler<in TEvent>
{
    Task HandleAsync(TEvent integrationEvent, string messageId, CancellationToken cancellationToken = default);
}
