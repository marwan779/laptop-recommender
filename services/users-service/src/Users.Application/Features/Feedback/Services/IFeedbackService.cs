using Users.Application.Common.Models;
using Users.Application.Features.Feedback.DTOs;

namespace Users.Application.Features.Feedback.Services;

public interface IFeedbackService
{
    Task<Result<FeedbackResponse>> SubmitAsync(
        Guid? userId,
        string? authenticatedEmail,
        CreateFeedbackRequest request,
        CancellationToken cancellationToken = default);

    Task<Result<IReadOnlyList<FeedbackResponse>>> GetMyReportsAsync(
        Guid userId,
        int limit = 50,
        CancellationToken cancellationToken = default);

    Task<Result<IReadOnlyList<FeedbackResponse>>> ListAllForAdminAsync(
        string? status = null,
        string? category = null,
        int limit = 50,
        int offset = 0,
        CancellationToken cancellationToken = default);

    Task<Result<FeedbackResponse>> ReviewAsync(
        Guid adminUserId,
        Guid feedbackId,
        UpdateFeedbackStatusRequest request,
        CancellationToken cancellationToken = default);
}
