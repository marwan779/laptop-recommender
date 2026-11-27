using Users.Application.Common.Models;
using Users.Application.Features.Wishlist.DTOs;

namespace Users.Application.Features.Wishlist.Services;

public interface IWishlistService
{
    Task<Result<IReadOnlyList<WishlistItemResponse>>> GetMyWishlistAsync(
        Guid userId,
        CancellationToken cancellationToken = default);

    Task<Result<WishlistItemResponse>> AddAsync(
        Guid userId,
        AddWishlistItemRequest request,
        CancellationToken cancellationToken = default);

    Task<Result<WishlistItemResponse>> UpdatePreferencesAsync(
        Guid userId,
        string canonicalId,
        UpdateWishlistPreferencesRequest request,
        CancellationToken cancellationToken = default);

    Task<Result> RemoveByCanonicalIdAsync(
        Guid userId,
        string canonicalId,
        CancellationToken cancellationToken = default);
}
