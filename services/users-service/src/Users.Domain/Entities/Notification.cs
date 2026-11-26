using Users.Domain.Common;

namespace Users.Domain.Entities;

public sealed class Notification : BaseEntity
{
    public Guid UserId { get; private set; }
    public User? User { get; private set; }
    public string CanonicalId { get; private set; } = string.Empty;
    public string Title { get; private set; } = string.Empty;
    public string Message { get; private set; } = string.Empty;
    public string ChangeType { get; private set; } = string.Empty;
    public decimal? OldPriceEgp { get; private set; }
    public decimal? NewPriceEgp { get; private set; }
    public string? CheapestStore { get; private set; }
    public bool IsRead { get; private set; }
    public DateTime? ReadAtUtc { get; private set; }

    private Notification() { }

    private Notification(
        Guid userId,
        string canonicalId,
        string title,
        string message,
        string changeType,
        decimal? oldPriceEgp,
        decimal? newPriceEgp,
        string? cheapestStore)
    {
        UserId = userId;
        CanonicalId = canonicalId;
        Title = title;
        Message = message;
        ChangeType = changeType;
        OldPriceEgp = oldPriceEgp;
        NewPriceEgp = newPriceEgp;
        CheapestStore = cheapestStore;
        IsRead = false;
    }

    public static Notification Create(
        Guid userId,
        string canonicalId,
        string title,
        string message,
        string changeType,
        decimal? oldPriceEgp = null,
        decimal? newPriceEgp = null,
        string? cheapestStore = null)
    {
        if (userId == Guid.Empty)
        {
            throw new DomainException("UserId is required.");
        }

        var cleanCanonicalId = (canonicalId ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanCanonicalId) || cleanCanonicalId.Length > 160)
        {
            throw new DomainException("A valid CanonicalId (1-160 chars) is required.");
        }

        var cleanTitle = (title ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanTitle))
        {
            throw new DomainException("Title is required.");
        }

        if (cleanTitle.Length > 300)
        {
            cleanTitle = cleanTitle[..300];
        }

        var cleanMessage = (message ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanMessage))
        {
            throw new DomainException("Message is required.");
        }

        if (cleanMessage.Length > 1000)
        {
            cleanMessage = cleanMessage[..1000];
        }

        var cleanChangeType = (changeType ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanChangeType) || cleanChangeType.Length > 50)
        {
            throw new DomainException("A valid ChangeType (1-50 chars) is required.");
        }

        if (oldPriceEgp is < 0)
        {
            throw new DomainException("OldPriceEgp cannot be negative.");
        }

        if (newPriceEgp is < 0)
        {
            throw new DomainException("NewPriceEgp cannot be negative.");
        }

        var cleanStore = string.IsNullOrWhiteSpace(cheapestStore) ? null : cheapestStore.Trim();
        if (cleanStore is not null && cleanStore.Length > 120)
        {
            cleanStore = cleanStore[..120];
        }

        return new Notification(
            userId,
            cleanCanonicalId,
            cleanTitle,
            cleanMessage,
            cleanChangeType,
            oldPriceEgp,
            newPriceEgp,
            cleanStore);
    }

    public void MarkAsRead(DateTime utcNow)
    {
        if (IsRead)
        {
            return;
        }

        IsRead = true;
        ReadAtUtc = utcNow;
        TouchUpdatedAt(utcNow);
    }
}
