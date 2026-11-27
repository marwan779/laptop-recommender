using Users.Domain.Common;

namespace Users.Domain.Entities;

public sealed class InboxMessage
{
    public string MessageId { get; private set; } = string.Empty;
    public string RoutingKey { get; private set; } = string.Empty;
    public DateTime ProcessedAtUtc { get; private set; }

    private InboxMessage() { }

    private InboxMessage(string messageId, string routingKey, DateTime processedAtUtc)
    {
        MessageId = messageId;
        RoutingKey = routingKey;
        ProcessedAtUtc = processedAtUtc;
    }

    public static InboxMessage Create(string messageId, string routingKey, DateTime processedAtUtc)
    {
        var cleanId = (messageId ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanId) || cleanId.Length > 128)
        {
            throw new DomainException("A valid MessageId (1-128 chars) is required.");
        }

        var cleanKey = (routingKey ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanKey) || cleanKey.Length > 128)
        {
            throw new DomainException("A valid RoutingKey (1-128 chars) is required.");
        }

        return new InboxMessage(cleanId, cleanKey, processedAtUtc);
    }
}
