namespace Users.Application.Features.Feedback.DTOs;

public sealed record CreateFeedbackRequest(
    string Category,
    string Title,
    string Description,
    string? ReporterEmail = null,
    string? CanonicalId = null,
    string? LaptopTitleSnapshot = null,
    string? PageUrl = null);

public sealed record UpdateFeedbackStatusRequest(
    string Status,
    string? AdminNotes = null);

public sealed record FeedbackResponse(
    Guid Id,
    Guid? UserId,
    string? ReporterEmail,
    string Category,
    string? CanonicalId,
    string? LaptopTitleSnapshot,
    string Title,
    string Description,
    string? PageUrl,
    string Status,
    string? AdminNotes,
    Guid? ResolvedByUserId,
    DateTime? ResolvedAtUtc,
    DateTime CreatedAtUtc,
    DateTime? UpdatedAtUtc);
