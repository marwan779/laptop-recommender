namespace Users.Application.Features.Notifications.DTOs;

public sealed record NotificationResponse(
    Guid Id,
    string CanonicalId,
    string Title,
    string Message,
    string ChangeType,
    decimal? OldPriceEgp,
    decimal? NewPriceEgp,
    string? CheapestStore,
    bool IsRead,
    DateTime? ReadAtUtc,
    DateTime CreatedAtUtc);

public sealed record NotificationListResponse(
    IReadOnlyList<NotificationResponse> Items,
    int UnreadCount);

public sealed record UnreadCountResponse(int UnreadCount);

public sealed record MarkAllReadResponse(int MarkedCount);

public sealed record ClearAllNotificationsResponse(int DeletedCount);
