using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Notifications.DTOs;
using Users.Domain.Entities;

namespace Users.Application.Features.Notifications.Services;

public sealed class NotificationService(
    INotificationRepository notificationRepository,
    IUnitOfWork unitOfWork,
    IDateTimeProvider dateTimeProvider,
    ICacheProvider cacheProvider) : INotificationService
{
    public async Task<Result<NotificationListResponse>> GetMyNotificationsAsync(
        Guid userId,
        bool unreadOnly = false,
        int limit = 50,
        CancellationToken cancellationToken = default)
    {
        var items = await notificationRepository.GetByUserIdAsync(userId, unreadOnly, limit, cancellationToken);
        var unreadCount = await notificationRepository.GetUnreadCountAsync(userId, cancellationToken);

        return Result<NotificationListResponse>.Success(new NotificationListResponse(
            items.Select(MapToResponse).ToList(),
            unreadCount));
    }

    public async Task<Result<UnreadCountResponse>> GetUnreadCountAsync(
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        var unreadCount = await notificationRepository.GetUnreadCountAsync(userId, cancellationToken);
        return Result<UnreadCountResponse>.Success(new UnreadCountResponse(unreadCount));
    }

    public async Task<Result<NotificationResponse>> MarkAsReadAsync(
        Guid userId,
        Guid notificationId,
        CancellationToken cancellationToken = default)
    {
        var notification = await notificationRepository.GetByIdAndUserIdAsync(
            notificationId,
            userId,
            cancellationToken);

        if (notification is null)
        {
            return Result<NotificationResponse>.NotFound("Notification was not found.");
        }

        if (!notification.IsRead)
        {
            notification.MarkAsRead(dateTimeProvider.UtcNow);
            await unitOfWork.SaveChangesAsync(cancellationToken);
            await InvalidateUserNotificationsAsync(userId, cancellationToken);
        }

        return Result<NotificationResponse>.Success(MapToResponse(notification));
    }

    public async Task<Result<MarkAllReadResponse>> MarkAllAsReadAsync(
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        var markedCount = await notificationRepository.MarkAllAsReadAsync(
            userId,
            dateTimeProvider.UtcNow,
            cancellationToken);

        await InvalidateUserNotificationsAsync(userId, cancellationToken);
        return Result<MarkAllReadResponse>.Success(new MarkAllReadResponse(markedCount));
    }

    public async Task<Result<ClearAllNotificationsResponse>> ClearAllAsync(
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        var deletedCount = await notificationRepository.DeleteAllByUserIdAsync(userId, cancellationToken);
        await InvalidateUserNotificationsAsync(userId, cancellationToken);
        return Result<ClearAllNotificationsResponse>.Success(new ClearAllNotificationsResponse(deletedCount));
    }

    private Task<int> InvalidateUserNotificationsAsync(Guid userId, CancellationToken cancellationToken)
        => cacheProvider.ClearPrefixAsync($"users:{userId}:notifications:", cancellationToken);

    private static NotificationResponse MapToResponse(Notification n)
        => new(
            n.Id,
            n.CanonicalId,
            n.Title,
            n.Message,
            n.ChangeType,
            n.OldPriceEgp,
            n.NewPriceEgp,
            n.CheapestStore,
            n.IsRead,
            n.ReadAtUtc,
            n.CreatedAtUtc);
}
