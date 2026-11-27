namespace Users.Application.Features.Auth.DTOs;

public sealed record RegisterRequest(
    string Email,
    string FullName,
    string Password,
    string PreferredLanguage = "ar");
