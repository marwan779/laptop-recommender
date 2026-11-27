using Microsoft.Extensions.Logging;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Jobs;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Feedback.DTOs;
using Users.Domain.Common;
using Users.Domain.Entities;

namespace Users.Application.Features.Feedback.Services;

public sealed class FeedbackService(
    IFeedbackRepository feedbackRepository,
    IUserRepository userRepository,
    INotificationRepository notificationRepository,
    IUnitOfWork unitOfWork,
    IDateTimeProvider dateTimeProvider,
    ICacheProvider cacheProvider,
    IBackgroundJobScheduler backgroundJobScheduler,
    ILogger<FeedbackService> logger) : IFeedbackService
{
    public async Task<Result<FeedbackResponse>> SubmitAsync(
        Guid? userId,
        string? authenticatedEmail,
        CreateFeedbackRequest request,
        CancellationToken cancellationToken = default)
    {
        FeedbackReport report;
        try
        {
            var effectiveEmail = !string.IsNullOrWhiteSpace(authenticatedEmail)
                ? authenticatedEmail
                : request.ReporterEmail;

            report = FeedbackReport.Create(
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
        }
        catch (DomainException ex)
        {
            return Result<FeedbackResponse>.Validation(ex.Message);
        }

        await NotifyAdminsAsync(report, cancellationToken);
        return Result<FeedbackResponse>.Success(MapToResponse(report));
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
        }
        catch (DomainException ex)
        {
            return Result<FeedbackResponse>.Validation(ex.Message);
        }

        await NotifyReporterAsync(report, cancellationToken);
        return Result<FeedbackResponse>.Success(MapToResponse(report));
    }

    private async Task NotifyAdminsAsync(FeedbackReport report, CancellationToken cancellationToken)
    {
        try
        {
            var admins = await userRepository.ListActiveAdminsAsync(cancellationToken);
            if (admins.Count == 0)
            {
                return;
            }

            var reporterLabel = string.IsNullOrWhiteSpace(report.ReporterEmail)
                ? "Guest"
                : report.ReporterEmail;
            var notifications = admins
                .Select(admin => Notification.Create(
                    admin.Id,
                    report.CanonicalId ?? "feedback-report",
                    $"New report ({report.Category}): {report.Title}",
                    $"Submitted by {reporterLabel}: {report.Description}",
                    "FEEDBACK_NEW"))
                .ToList();

            await notificationRepository.AddRangeAsync(notifications, cancellationToken);
            await unitOfWork.SaveChangesAsync(cancellationToken);

            foreach (var admin in admins)
            {
                await cacheProvider.ClearPrefixAsync($"users:{admin.Id}:notifications:", cancellationToken);
                backgroundJobScheduler.EnqueueFeedbackAdminAlertEmail(new FeedbackAdminAlertEmailPayload(
                    admin.Email,
                    admin.FullName,
                    report.Id,
                    report.Category,
                    report.Title,
                    report.Description,
                    report.ReporterEmail,
                    report.LaptopTitleSnapshot));
            }
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to dispatch admin alerts for feedback report {ReportId}", report.Id);
        }
    }

    private async Task NotifyReporterAsync(FeedbackReport report, CancellationToken cancellationToken)
    {
        try
        {
            User? reporter = null;
            if (report.UserId.HasValue)
            {
                reporter = await userRepository.GetByIdWithRoleAsync(report.UserId.Value, cancellationToken);

                var notesPart = string.IsNullOrWhiteSpace(report.AdminNotes)
                    ? string.Empty
                    : $" — {report.AdminNotes}";
                var notification = Notification.Create(
                    report.UserId.Value,
                    report.CanonicalId ?? "feedback-report",
                    $"Report {report.Status}: {report.Title}",
                    $"Your {report.Category} report status changed to {report.Status}{notesPart}",
                    $"FEEDBACK_{report.Status}");

                await notificationRepository.AddRangeAsync([notification], cancellationToken);
                await unitOfWork.SaveChangesAsync(cancellationToken);
                await cacheProvider.ClearPrefixAsync($"users:{report.UserId.Value}:notifications:", cancellationToken);
            }

            var recipientEmail = reporter?.Email ?? report.ReporterEmail;
            if (!string.IsNullOrWhiteSpace(recipientEmail))
            {
                backgroundJobScheduler.EnqueueFeedbackReviewedEmail(new FeedbackReviewedEmailPayload(
                    recipientEmail,
                    reporter?.FullName ?? "there",
                    reporter?.PreferredLanguage ?? "en",
                    report.Id,
                    report.Category,
                    report.Title,
                    report.Status,
                    report.AdminNotes,
                    report.LaptopTitleSnapshot));
            }
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to dispatch reporter alerts for feedback report {ReportId}", report.Id);
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
