using Users.Domain.Common;

namespace Users.Domain.Entities;

public sealed class Role : BaseEntity
{
    public static readonly Guid UserRoleId = Guid.Parse("11111111-1111-1111-1111-111111111111");
    public static readonly Guid AdminRoleId = Guid.Parse("22222222-2222-2222-2222-222222222222");

    public string Name { get; private set; } = string.Empty;
    public string? Description { get; private set; }

    private readonly List<User> _users = [];
    public IReadOnlyCollection<User> Users => _users.AsReadOnly();

    private Role() { }

    private Role(Guid id, string name, string? description)
    {
        Id = id;
        Name = name;
        Description = description;
    }

    public static Role Create(string name, string? description = null, Guid? id = null)
    {
        var trimmed = name?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(trimmed))
        {
            throw new DomainException("Role name cannot be empty.");
        }

        if (trimmed.Length > 32)
        {
            throw new DomainException("Role name cannot exceed 32 characters.");
        }

        return new Role(id ?? Guid.NewGuid(), trimmed, description?.Trim());
    }
}
