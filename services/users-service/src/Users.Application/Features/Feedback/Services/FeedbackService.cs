using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Feedback.DTOs;
using Users.Domain.Common;
using Users.Domain.Entities;

namespace Users.Application.Features.Feedback.Services;

public sealed class FeedbackService(
    IFeedbackRepository feedbackRepository,
    IUnitOfWork unitOfWork,
    IDateTimeProvider dateTimeProvider) : IFeedbackService
{
    public async Task<Result<FeedbackResponse>> SubmitAsync(
        Guid? userId,
        string? authenticatedEmail,
        CreateFeedbackRequest request,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var effectiveEmail = !string.IsNullOrWhiteSpace(authenticatedEmail)
                ? authenticatedEmail
                : request.ReporterEmail;

            var report = FeedbackReport.Create(
                userId,
                effectiveEmail,
                request.Category,
                request.Title,
                request.Description,
                request.CanonicalId,
                request.LaptopTitleSnapshot,
                request.PageUrl);

            await feedbackRepository.AddAsync(report, cancellationToken);
            await unitOfWork.SaveChangesAsync(cancellationToken);

            return Result<FeedbackResponse>.Success(MapToResponse(report));
        }
        catch (DomainException ex)
        {
            return Result<FeedbackResponse>.Validation(ex.Message);
        }
    }

    public async Task<Result<IReadOnlyList<FeedbackResponse>>> GetMyReportsAsync(
        Guid userId,
        int limit = 50,
        CancellationToken cancellationToken = default)
    {
        var items = await feedbackRepository.GetByUserIdAsync(userId, limit, cancellationToken);
        return Result<IReadOnlyList<FeedbackResponse>>.Success(items.Select(MapToResponse).ToList());
    }

    public async Task<Result<IReadOnlyList<FeedbackResponse>>> ListAllForAdminAsync(
        string? status = null,
        string? category = null,
        int limit = 50,
        int offset = 0,
        CancellationToken cancellationToken = default)
    {
        var items = await feedbackRepository.ListAsync(status, category, limit, offset, cancellationToken);
        return Result<IReadOnlyList<FeedbackResponse>>.Success(items.Select(MapToResponse).ToList());
    }

    public async Task<Result<FeedbackResponse>> ReviewAsync(
        Guid adminUserId,
        Guid feedbackId,
        UpdateFeedbackStatusRequest request,
        CancellationToken cancellationToken = default)
    {
        var report = await feedbackRepository.GetByIdAsync(feedbackId, cancellationToken);
        if (report is null)
        {
            return Result<FeedbackResponse>.NotFound("Feedback report was not found.");
        }

        try
        {
            report.UpdateReview(request.Status, request.AdminNotes, adminUserId, dateTimeProvider.UtcNow);
            await unitOfWork.SaveChangesAsync(cancellationToken);
            return Result<FeedbackResponse>.Success(MapToResponse(report));
        }
        catch (DomainException ex)
        {
            return Result<FeedbackResponse>.Validation(ex.Message);
        }
    }

    private static FeedbackResponse MapToResponse(FeedbackReport r)
        => new(
            r.Id,
            r.UserId,
            r.ReporterEmail,
            r.Category,
            r.CanonicalId,
            r.LaptopTitleSnapshot,
            r.Title,
            r.Description,
            r.PageUrl,
            r.Status,
            r.AdminNotes,
            r.ResolvedByUserId,
            r.ResolvedAtUtc,
            r.CreatedAtUtc,
            r.UpdatedAtUtc);
}
