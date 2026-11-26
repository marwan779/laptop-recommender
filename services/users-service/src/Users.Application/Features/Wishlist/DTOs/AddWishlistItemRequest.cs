namespace Users.Application.Features.Wishlist.DTOs;

public sealed record AddWishlistItemRequest(
    string CanonicalId,
    string TitleSnapshot,
    decimal AddedPriceEgp,
    string? ThumbnailUrlSnapshot = null,
    decimal? TargetPriceEgp = null,
    bool NotifyOnPriceDrop = true,
    bool NotifyOnAnyChange = false,
    bool NotifyOnRestock = true);
