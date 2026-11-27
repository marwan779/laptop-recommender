namespace Users.Infrastructure.Persistence.Seeding;

public sealed class AdminSeedOptions
{
    public const string SectionName = "AdminSeed";

    public bool Enabled { get; set; } = true;
    public string Email { get; set; } = "marwanmohamed3337@gmail.com";
    public string FullName { get; set; } = "Marwan Mohamed";
    public string Password { get; set; } = string.Empty;
}
