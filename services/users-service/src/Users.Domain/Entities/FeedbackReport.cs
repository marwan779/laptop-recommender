using Users.Domain.Common;

namespace Users.Domain.Entities;

public static class FeedbackCategories
{
    public const string WrongPrice = "WRONG_PRICE";
    public const string WrongSpec = "WRONG_SPEC";
    public const string BrokenLink = "BROKEN_LINK";
    public const string MissingLaptop = "MISSING_LAPTOP";
    public const string UiBug = "UI_BUG";
    public const string Other = "OTHER";

    public static readonly HashSet<string> Allowed = new(StringComparer.OrdinalIgnoreCase)
    {
        WrongPrice,
        WrongSpec,
        BrokenLink,
        MissingLaptop,
        UiBug,
        Other,
    };
}

public static class FeedbackStatuses
{
    public const string Open = "OPEN";
    public const string InReview = "IN_REVIEW";
    public const string Resolved = "RESOLVED";
    public const string Dismissed = "DISMISSED";

    public static readonly HashSet<string> Allowed = new(StringComparer.OrdinalIgnoreCase)
    {
        Open,
        InReview,
        Resolved,
        Dismissed,
    };
}

public sealed class FeedbackReport : BaseEntity
{
    public Guid? UserId { get; private set; }
    public User? User { get; private set; }
    public string? ReporterEmail { get; private set; }
    public string Category { get; private set; } = FeedbackCategories.Other;
    public string? CanonicalId { get; private set; }
    public string? LaptopTitleSnapshot { get; private set; }
    public string Title { get; private set; } = string.Empty;
    public string Description { get; private set; } = string.Empty;
    public string? PageUrl { get; private set; }
    public string Status { get; private set; } = FeedbackStatuses.Open;
    public string? AdminNotes { get; private set; }
    public Guid? ResolvedByUserId { get; private set; }
    public DateTime? ResolvedAtUtc { get; private set; }

    private FeedbackReport() { }

    private FeedbackReport(
        Guid? userId,
        string? reporterEmail,
        string category,
        string? canonicalId,
        string? laptopTitleSnapshot,
        string title,
        string description,
        string? pageUrl)
    {
        UserId = userId;
        ReporterEmail = reporterEmail;
        Category = category;
        CanonicalId = canonicalId;
        LaptopTitleSnapshot = laptopTitleSnapshot;
        Title = title;
        Description = description;
        PageUrl = pageUrl;
        Status = FeedbackStatuses.Open;
    }

    public static FeedbackReport Create(
        Guid? userId,
        string? reporterEmail,
        string category,
        string title,
        string description,
        string? canonicalId = null,
        string? laptopTitleSnapshot = null,
        string? pageUrl = null)
    {
        var normalizedCategory = (category ?? string.Empty).Trim().ToUpperInvariant();
        if (!FeedbackCategories.Allowed.Contains(normalizedCategory))
        {
            throw new DomainException("Invalid feedback category.");
        }

        var cleanTitle = (title ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanTitle) || cleanTitle.Length > 200)
        {
            throw new DomainException("Feedback title (1-200 chars) is required.");
        }

        var cleanDescription = (description ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanDescription) || cleanDescription.Length > 2000)
        {
            throw new DomainException("Feedback description (1-2000 chars) is required.");
        }

        var cleanEmail = string.IsNullOrWhiteSpace(reporterEmail) ? null : reporterEmail.Trim().ToLowerInvariant();
        if (cleanEmail is not null && (cleanEmail.Length > 256 || !cleanEmail.Contains('@')))
        {
            throw new DomainException("Invalid reporter email address.");
        }

        var cleanCanonicalId = string.IsNullOrWhiteSpace(canonicalId) ? null : canonicalId.Trim();
        if (cleanCanonicalId is not null && cleanCanonicalId.Length > 160)
        {
            cleanCanonicalId = cleanCanonicalId[..160];
        }

        var cleanLaptopTitle = string.IsNullOrWhiteSpace(laptopTitleSnapshot) ? null : laptopTitleSnapshot.Trim();
        if (cleanLaptopTitle is not null && cleanLaptopTitle.Length > 300)
        {
            cleanLaptopTitle = cleanLaptopTitle[..300];
        }

        var cleanPageUrl = string.IsNullOrWhiteSpace(pageUrl) ? null : pageUrl.Trim();
        if (cleanPageUrl is not null && cleanPageUrl.Length > 500)
        {
            cleanPageUrl = cleanPageUrl[..500];
        }

        return new FeedbackReport(
            userId is null || userId == Guid.Empty ? null : userId,
            cleanEmail,
            normalizedCategory,
            cleanCanonicalId,
            cleanLaptopTitle,
            cleanTitle,
            cleanDescription,
            cleanPageUrl);
    }

    public void UpdateReview(
        string status,
        string? adminNotes,
        Guid adminUserId,
        DateTime utcNow)
    {
        var normalizedStatus = (status ?? string.Empty).Trim().ToUpperInvariant();
        if (!FeedbackStatuses.Allowed.Contains(normalizedStatus))
        {
            throw new DomainException("Invalid feedback status.");
        }

        if (adminUserId == Guid.Empty)
        {
            throw new DomainException("AdminUserId is required.");
        }

        var cleanNotes = string.IsNullOrWhiteSpace(adminNotes) ? null : adminNotes.Trim();
        if (cleanNotes is not null && cleanNotes.Length > 1000)
        {
            cleanNotes = cleanNotes[..1000];
        }

        Status = normalizedStatus;
        AdminNotes = cleanNotes;
        ResolvedByUserId = adminUserId;
        ResolvedAtUtc = normalizedStatus is FeedbackStatuses.Resolved or FeedbackStatuses.Dismissed
            ? utcNow
            : null;
        TouchUpdatedAt(utcNow);
    }
}
