using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Users.Application.Features.Notifications.DTOs;
using Users.Application.Features.Notifications.Services;

namespace Users.Api.Areas.Users.Controllers;

[Authorize]
public sealed class NotificationsController(INotificationService notificationService) : UsersBaseController
{
    [HttpGet]
    [ProducesResponseType(typeof(NotificationListResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<IActionResult> GetMyNotifications(
        [FromQuery] bool unreadOnly = false,
        [FromQuery] int limit = 50,
        CancellationToken cancellationToken = default)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await notificationService.GetMyNotificationsAsync(userId.Value, unreadOnly, limit, cancellationToken);
        return ToActionResult(result);
    }

    [HttpGet("unread-count")]
    [ProducesResponseType(typeof(UnreadCountResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<IActionResult> GetUnreadCount(CancellationToken cancellationToken)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await notificationService.GetUnreadCountAsync(userId.Value, cancellationToken);
        return ToActionResult(result);
    }

    [HttpPatch("{notificationId:guid}/read")]
    [ProducesResponseType(typeof(NotificationResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> MarkAsRead(
        Guid notificationId,
        CancellationToken cancellationToken)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await notificationService.MarkAsReadAsync(userId.Value, notificationId, cancellationToken);
        return ToActionResult(result);
    }

    [HttpPatch("read-all")]
    [ProducesResponseType(typeof(MarkAllReadResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<IActionResult> MarkAllAsRead(CancellationToken cancellationToken)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await notificationService.MarkAllAsReadAsync(userId.Value, cancellationToken);
        return ToActionResult(result);
    }

    [HttpDelete]
    [ProducesResponseType(typeof(ClearAllNotificationsResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<IActionResult> ClearAll(CancellationToken cancellationToken)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await notificationService.ClearAllAsync(userId.Value, cancellationToken);
        return ToActionResult(result);
    }
}
