namespace Users.Application.Features.Auth.DTOs;

public sealed record AuthResponse(
    string AccessToken,
    string RefreshToken,
    Guid UserId,
    string Email,
    string FullName,
    string Role,
    string PreferredLanguage);
