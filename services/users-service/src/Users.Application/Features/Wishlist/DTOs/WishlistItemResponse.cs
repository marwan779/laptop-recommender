namespace Users.Application.Features.Wishlist.DTOs;

public sealed record WishlistItemResponse(
    Guid Id,
    string CanonicalId,
    string TitleSnapshot,
    string? ThumbnailUrlSnapshot,
    decimal AddedPriceEgp,
    decimal? LastNotifiedPriceEgp,
    decimal? TargetPriceEgp,
    bool NotifyOnPriceDrop,
    bool NotifyOnAnyChange,
    bool NotifyOnRestock,
    DateTime CreatedAtUtc,
    DateTime? UpdatedAtUtc);
