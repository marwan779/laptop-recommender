using Users.Application.Common.Models;
using Users.Application.Features.Notifications.DTOs;

namespace Users.Application.Features.Notifications.Services;

public interface INotificationService
{
    Task<Result<NotificationListResponse>> GetMyNotificationsAsync(
        Guid userId,
        bool unreadOnly = false,
        int limit = 50,
        CancellationToken cancellationToken = default);

    Task<Result<UnreadCountResponse>> GetUnreadCountAsync(
        Guid userId,
        CancellationToken cancellationToken = default);

    Task<Result<NotificationResponse>> MarkAsReadAsync(
        Guid userId,
        Guid notificationId,
        CancellationToken cancellationToken = default);

    Task<Result<MarkAllReadResponse>> MarkAllAsReadAsync(
        Guid userId,
        CancellationToken cancellationToken = default);

    Task<Result<ClearAllNotificationsResponse>> ClearAllAsync(
        Guid userId,
        CancellationToken cancellationToken = default);
}
