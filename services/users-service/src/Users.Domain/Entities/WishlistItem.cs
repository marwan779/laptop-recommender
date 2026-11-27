using Users.Domain.Common;

namespace Users.Domain.Entities;

public sealed class WishlistItem : BaseEntity
{
    public Guid UserId { get; private set; }
    public User? User { get; private set; }
    public string CanonicalId { get; private set; } = string.Empty;
    public string TitleSnapshot { get; private set; } = string.Empty;
    public string? ThumbnailUrlSnapshot { get; private set; }
    public decimal AddedPriceEgp { get; private set; }
    public decimal? LastNotifiedPriceEgp { get; private set; }
    public decimal? TargetPriceEgp { get; private set; }
    public bool NotifyOnPriceDrop { get; private set; } = true;
    public bool NotifyOnAnyChange { get; private set; }
    public bool NotifyOnRestock { get; private set; } = true;

    private WishlistItem() { }

    private WishlistItem(
        Guid userId,
        string canonicalId,
        string titleSnapshot,
        string? thumbnailUrlSnapshot,
        decimal addedPriceEgp,
        decimal? targetPriceEgp,
        bool notifyOnPriceDrop,
        bool notifyOnAnyChange,
        bool notifyOnRestock)
    {
        UserId = userId;
        CanonicalId = canonicalId;
        TitleSnapshot = titleSnapshot;
        ThumbnailUrlSnapshot = thumbnailUrlSnapshot;
        AddedPriceEgp = addedPriceEgp;
        TargetPriceEgp = targetPriceEgp;
        NotifyOnPriceDrop = notifyOnPriceDrop;
        NotifyOnAnyChange = notifyOnAnyChange;
        NotifyOnRestock = notifyOnRestock;
    }

    public static WishlistItem Create(
        Guid userId,
        string canonicalId,
        string titleSnapshot,
        decimal addedPriceEgp,
        string? thumbnailUrlSnapshot = null,
        decimal? targetPriceEgp = null,
        bool notifyOnPriceDrop = true,
        bool notifyOnAnyChange = false,
        bool notifyOnRestock = true)
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

        var cleanTitle = (titleSnapshot ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanTitle))
        {
            throw new DomainException("TitleSnapshot is required.");
        }

        if (cleanTitle.Length > 300)
        {
            cleanTitle = cleanTitle[..300];
        }

        if (addedPriceEgp < 0)
        {
            throw new DomainException("AddedPriceEgp cannot be negative.");
        }

        if (targetPriceEgp is <= 0)
        {
            throw new DomainException("TargetPriceEgp must be greater than zero when specified.");
        }

        return new WishlistItem(
            userId,
            cleanCanonicalId,
            cleanTitle,
            string.IsNullOrWhiteSpace(thumbnailUrlSnapshot) ? null : thumbnailUrlSnapshot.Trim(),
            addedPriceEgp,
            targetPriceEgp,
            notifyOnPriceDrop,
            notifyOnAnyChange,
            notifyOnRestock);
    }

    public void UpdatePreferences(
        decimal? targetPriceEgp,
        bool notifyOnPriceDrop,
        bool notifyOnAnyChange,
        bool notifyOnRestock,
        DateTime utcNow)
    {
        if (targetPriceEgp is <= 0)
        {
            throw new DomainException("TargetPriceEgp must be greater than zero when specified.");
        }

        TargetPriceEgp = targetPriceEgp;
        NotifyOnPriceDrop = notifyOnPriceDrop;
        NotifyOnAnyChange = notifyOnAnyChange;
        NotifyOnRestock = notifyOnRestock;
        TouchUpdatedAt(utcNow);
    }

    public void RecordNotificationSent(decimal? notifiedPriceEgp, DateTime utcNow)
    {
        LastNotifiedPriceEgp = notifiedPriceEgp;
        TouchUpdatedAt(utcNow);
    }
}
