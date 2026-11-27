namespace Users.Application.Features.Wishlist.DTOs;

public sealed record UpdateWishlistPreferencesRequest(
    decimal? TargetPriceEgp,
    bool NotifyOnPriceDrop,
    bool NotifyOnAnyChange,
    bool NotifyOnRestock);
