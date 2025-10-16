"""Main entry point for POV Email Generator."""

import json
from src.pov_gen_agent import generate_email
from src.pov_gen_agent.state import ProfileData


def main():
    """Run the POV Email Generator with example data."""

    # Example profile data
    profile_data: ProfileData = {
        "company": "Acme Corp",
        "company_size": 500,
        "industry": "B2B SaaS",
        "recent_news": "Just crossed 500 employees and expanded into enterprise market",
        "person_name": "Michael Wonder",
        "person_title": "VP of Sales Operations",
        "person_background": "Former sales ops leader at two unicorn startups",
    }

    print("\n🚀 POV Email Generator")
    print("=" * 60)
    print("\nTarget Profile:")
    print(f"  Company: {profile_data['company']}")
    print(f"  Contact: {profile_data['person_name']} ({profile_data['person_title']})")
    print(f"  Context: {profile_data.get('recent_news', 'N/A')}")
    print("\n" + "=" * 60)

    # Generate email
    result = generate_email(profile_data, verbose=True)

    # Save result to file
    output_file = "output_email.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n✓ Result saved to {output_file}")
    print("\n" + "=" * 60)


def custom_profile():
    """Generate email for a custom profile (modify this function as needed)."""

    # Customize this profile data
    profile_data: ProfileData = {
        "company": "Your Company Name",
        "company_size": 750,
        "industry": "Technology",
        "recent_news": "Recent funding or news",
        "person_name": "John Doe",
        "person_title": "CRO",
        "person_background": "Background information",
    }

    result = generate_email(profile_data, verbose=True)
    return result


if __name__ == "__main__":
    main()
