namespace Users.Application.Features.Auth.DTOs;

public sealed record UserProfileResponse(
    Guid UserId,
    string Email,
    string FullName,
    string Role,
    string PreferredLanguage,
    bool EmailVerified);
