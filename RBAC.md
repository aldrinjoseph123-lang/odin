# Role-Based Access Control (RBAC) Framework

## Overview
Fine-grained permission system with 3 roles (Admin, Member, Viewer) and 18 distinct permissions.

## Roles

### Admin
- Full system access
- Can perform all operations
- Manages users, settings, integrations

### Member
- Can view and create projects
- Can edit project details (stage, invoice, documents, notes)
- Can upload/download documents
- Read-only access to reports
- Cannot delete projects/documents or manage system settings

### Viewer
- Read-only access
- Can view board, projects, reports
- Cannot create, edit, or delete anything

## Permissions Matrix

| Permission | Admin | Member | Viewer |
|------------|-------|--------|--------|
| view_board | ✓ | ✓ | ✓ |
| view_projects | ✓ | ✓ | ✓ |
| view_project_detail | ✓ | ✓ | ✓ |
| create_project | ✓ | ✓ | ✗ |
| edit_project | ✓ | ✓ | ✗ |
| delete_project | ✓ | ✗ | ✗ |
| view_reports | ✓ | ✓ | ✓ |
| edit_project_stage | ✓ | ✓ | ✗ |
| edit_project_invoice | ✓ | ✓ | ✗ |
| edit_project_vendor_invoice | ✓ | ✓ | ✗ |
| add_project_note | ✓ | ✓ | ✗ |
| upload_document | ✓ | ✓ | ✗ |
| download_document | ✓ | ✓ | ✓ |
| delete_document | ✓ | ✗ | ✗ |
| manage_contacts | ✓ | ✗ | ✗ |
| manage_settings | ✓ | ✗ | ✗ |
| manage_users | ✓ | ✗ | ✗ |
| manage_integrations | ✓ | ✗ | ✗ |

## Implementation

### Defining Permissions
Permissions are defined in `app.py` in the `PERMISSIONS` dict:

```python
PERMISSIONS = {
    "view_board": ["Admin", "Member", "Viewer"],
    "create_project": ["Admin", "Member"],
    "delete_project": ["Admin"],
    # ... more permissions
}
```

### Permission Decorator
Use `@permission_required("permission_name")` on route handlers:

```python
@app.route("/projects/new", methods=["GET", "POST"])
@permission_required("create_project")
def project_new():
    # Implementation
```

### Checking Permissions at Runtime
The decorator checks if the user's role is in the allowed roles for that permission:

1. Verifies user is logged in (redirects to login if not)
2. Gets user's role from session
3. Checks if role has permission
4. Allows (200) or denies (403) access

## Usage

### For Users
- Log in with your account
- Your role determines what you can do
- Read-only actions available to Viewer role
- Creating/editing restricted to Admin/Member

### For Developers
1. Define new permission in `PERMISSIONS` dict
2. Add it to appropriate roles
3. Apply `@permission_required("permission_name")` decorator to route
4. Run tests to verify

## Legacy Decorators
- `@admin_required` - Replaced with `@permission_required("manage_*")`
- `@write_required` - Block Viewer role from mutations (still available for broad protection)

## Security Notes
- Permissions checked on every request
- 403 Forbidden returned for unauthorized access
- 401 Redirect to login for unauthenticated access
- User role stored in session after login
- All mutations require appropriate permission
