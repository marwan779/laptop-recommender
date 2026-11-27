using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Wishlist.DTOs;
using Users.Domain.Common;
using Users.Domain.Entities;

namespace Users.Application.Features.Wishlist.Services;

public sealed class WishlistService(
    IWishlistRepository wishlistRepository,
    IDateTimeProvider dateTimeProvider,
    IUnitOfWork unitOfWork,
    ICacheProvider cacheProvider) : IWishlistService
{
    public async Task<Result<IReadOnlyList<WishlistItemResponse>>> GetMyWishlistAsync(
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        var items = await wishlistRepository.GetByUserIdAsync(userId, cancellationToken);
        var response = items.Select(ToResponse).ToList();
        return Result<IReadOnlyList<WishlistItemResponse>>.Success(response);
    }

    public async Task<Result<WishlistItemResponse>> AddAsync(
        Guid userId,
        AddWishlistItemRequest request,
        CancellationToken cancellationToken = default)
    {
        var cleanCanonicalId = (request.CanonicalId ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanCanonicalId))
        {
            return Result<WishlistItemResponse>.Validation("CanonicalId is required.");
        }

        if (await wishlistRepository.ExistsAsync(userId, cleanCanonicalId, cancellationToken))
        {
            return Result<WishlistItemResponse>.Conflict("This laptop is already in your wishlist.");
        }

        WishlistItem item;
        try
        {
            item = WishlistItem.Create(
                userId: userId,
                canonicalId: cleanCanonicalId,
                titleSnapshot: request.TitleSnapshot,
                addedPriceEgp: request.AddedPriceEgp,
                thumbnailUrlSnapshot: request.ThumbnailUrlSnapshot,
                targetPriceEgp: request.TargetPriceEgp,
                notifyOnPriceDrop: request.NotifyOnPriceDrop,
                notifyOnAnyChange: request.NotifyOnAnyChange,
                notifyOnRestock: request.NotifyOnRestock);
        }
        catch (DomainException ex)
        {
            return Result<WishlistItemResponse>.Validation(ex.Message);
        }

        await wishlistRepository.AddAsync(item, cancellationToken);
        await unitOfWork.SaveChangesAsync(cancellationToken);
        await InvalidateUserWishlistAsync(userId, cancellationToken);

        return Result<WishlistItemResponse>.Success(ToResponse(item));
    }

    public async Task<Result<WishlistItemResponse>> UpdatePreferencesAsync(
        Guid userId,
        string canonicalId,
        UpdateWishlistPreferencesRequest request,
        CancellationToken cancellationToken = default)
    {
        var cleanCanonicalId = (canonicalId ?? string.Empty).Trim();
        var item = await wishlistRepository.GetByUserAndCanonicalIdAsync(userId, cleanCanonicalId, cancellationToken);
        if (item is null)
        {
            return Result<WishlistItemResponse>.NotFound("Wishlist item not found.");
        }

        try
        {
            item.UpdatePreferences(
                request.TargetPriceEgp,
                request.NotifyOnPriceDrop,
                request.NotifyOnAnyChange,
                request.NotifyOnRestock,
                dateTimeProvider.UtcNow);
        }
        catch (DomainException ex)
        {
            return Result<WishlistItemResponse>.Validation(ex.Message);
        }

        await unitOfWork.SaveChangesAsync(cancellationToken);
        await InvalidateUserWishlistAsync(userId, cancellationToken);
        return Result<WishlistItemResponse>.Success(ToResponse(item));
    }

    public async Task<Result> RemoveByCanonicalIdAsync(
        Guid userId,
        string canonicalId,
        CancellationToken cancellationToken = default)
    {
        var cleanCanonicalId = (canonicalId ?? string.Empty).Trim();
        var item = await wishlistRepository.GetByUserAndCanonicalIdAsync(userId, cleanCanonicalId, cancellationToken);
        if (item is null)
        {
            return Result.NotFound("Wishlist item not found.");
        }

        wishlistRepository.Remove(item);
        await unitOfWork.SaveChangesAsync(cancellationToken);
        await InvalidateUserWishlistAsync(userId, cancellationToken);
        return Result.Success();
    }

    private Task<int> InvalidateUserWishlistAsync(Guid userId, CancellationToken cancellationToken)
        => cacheProvider.ClearPrefixAsync($"users:{userId}:wishlist:", cancellationToken);

    private static WishlistItemResponse ToResponse(WishlistItem item) =>
        new(
            item.Id,
            item.CanonicalId,
            item.TitleSnapshot,
            item.ThumbnailUrlSnapshot,
            item.AddedPriceEgp,
            item.LastNotifiedPriceEgp,
            item.TargetPriceEgp,
            item.NotifyOnPriceDrop,
            item.NotifyOnAnyChange,
            item.NotifyOnRestock,
            item.CreatedAtUtc,
            item.UpdatedAtUtc);
}
