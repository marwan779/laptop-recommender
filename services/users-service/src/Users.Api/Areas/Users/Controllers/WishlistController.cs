using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Users.Application.Features.Wishlist.DTOs;
using Users.Application.Features.Wishlist.Services;

namespace Users.Api.Areas.Users.Controllers;

[Authorize]
public sealed class WishlistController(IWishlistService wishlistService) : UsersBaseController
{
    [HttpGet]
    [ProducesResponseType(typeof(IReadOnlyList<WishlistItemResponse>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<IActionResult> GetMyWishlist(CancellationToken cancellationToken)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await wishlistService.GetMyWishlistAsync(userId.Value, cancellationToken);
        return ToActionResult(result);
    }

    [HttpPost]
    [ProducesResponseType(typeof(WishlistItemResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<IActionResult> Add(
        [FromBody] AddWishlistItemRequest request,
        CancellationToken cancellationToken)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await wishlistService.AddAsync(userId.Value, request, cancellationToken);
        return ToActionResult(result);
    }

    [HttpPatch("{canonicalId}")]
    [ProducesResponseType(typeof(WishlistItemResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> UpdatePreferences(
        string canonicalId,
        [FromBody] UpdateWishlistPreferencesRequest request,
        CancellationToken cancellationToken)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await wishlistService.UpdatePreferencesAsync(
            userId.Value,
            canonicalId,
            request,
            cancellationToken);
        return ToActionResult(result);
    }

    [HttpDelete("{canonicalId}")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Remove(
        string canonicalId,
        CancellationToken cancellationToken)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await wishlistService.RemoveByCanonicalIdAsync(userId.Value, canonicalId, cancellationToken);
        return ToActionResult(result);
    }
}
