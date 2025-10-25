"""
Result Writer - exports processed leads to CSV.
"""

import csv
from pathlib import Path
from typing import List, Dict, Any


class ResultWriter:
    """
    Writes processing results to CSV file.
    """

    @staticmethod
    def write_results(tasks: List[Dict[str, Any]], output_path: str):
        """
        Write tasks to CSV file.

        Args:
            tasks: List of processed tasks
            output_path: Path to output CSV file
        """
        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            # Define CSV columns
            fieldnames = [
                # Lead basic info
                'email',
                'name',
                'company',
                'job_title',
                'linkedin_url',

                # Stage 1: Classification
                'stage1_relevant',
                'stage1_reason',

                # Stage 2: Letter Generation
                'stage2_status',
                'stage2_rejected',
                'stage2_rejection_reason',

                # Letter fields (only if accepted)
                'letter_subject',
                'letter_body',
                'letter_send_time_msk',
                'personalization_signals',

                # Assessment
                'relevance_assessment',
                'notes',

                # Meta
                'final_status',
                'error',
                'processed_at'
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for task in tasks:
                # Skip None tasks (shouldn't happen, but defensive programming)
                if not task:
                    continue

                lead_data = task.get('lead_data') or {}
                stage1 = task.get('stage1_result') or {}
                stage2 = task.get('stage2_result') or {}

                # Extract letter if present
                letter_data = stage2.get('letter') if stage2 else None
                letter = letter_data if isinstance(letter_data, dict) else {}

                # Determine final status
                final_status = ResultWriter._determine_final_status(task, stage1, stage2)

                # Format letter_body as: email\n\nsend_time\n\nsubject\n\nletter_text OR rejection reason
                letter_body = ''
                if stage2.get('rejected'):
                    # If rejected, show rejection reason
                    rejection_reason = stage2.get('reason', 'Not relevant')
                    letter_body = f"REJECTED: {rejection_reason}"
                elif letter:
                    # If accepted, format full letter: email, send_time, subject, body (with blank lines)
                    email = task.get('email', '')
                    send_time = letter.get('send_time_msk', '')
                    subject = letter.get('subject', '')
                    letter_text = letter.get('body', '')

                    letter_body = f"{email}\n\n{send_time}\n\n{subject}\n\n{letter_text}"

                row = {
                    # Lead basic info
                    'email': task.get('email'),
                    'name': lead_data.get('First Name') or lead_data.get('name'),
                    'company': lead_data.get('companyName') or lead_data.get('company'),
                    'job_title': lead_data.get('jobTitle') or lead_data.get('job_title'),
                    'linkedin_url': task.get('linkedin_url'),

                    # Stage 1
                    'stage1_relevant': 'Yes' if stage1.get('relevant') else 'No',
                    'stage1_reason': stage1.get('reason', ''),

                    # Stage 2
                    'stage2_status': 'completed' if stage2 else 'skipped',
                    'stage2_rejected': 'Yes' if stage2.get('rejected') else ('No' if stage2 else ''),
                    'stage2_rejection_reason': stage2.get('reason', '') if stage2.get('rejected') else '',

                    # Letter fields (combined format)
                    'letter_subject': letter.get('subject', ''),
                    'letter_body': letter_body,
                    'letter_send_time_msk': letter.get('send_time_msk', ''),
                    'personalization_signals': '; '.join(letter.get('personalization_signals', [])) if letter.get('personalization_signals') else '',

                    # Assessment
                    'relevance_assessment': stage2.get('relevance_assessment', ''),
                    'notes': stage2.get('notes', ''),

                    # Meta
                    'final_status': final_status,
                    'error': task.get('error', ''),
                    'processed_at': task.get('completed_at', '')
                }

                writer.writerow(row)

        return output_path

    @staticmethod
    def _determine_final_status(task: Dict, stage1: Dict, stage2: Dict) -> str:
        """
        Determine final status of lead processing.

        Returns:
            Status string: not_relevant, rejected, success, error, pending
        """
        status = task.get('status')

        if status == 'failed':
            return 'error'
        elif status == 'pending' or status == 'processing':
            return 'pending'

        # Check stage 1
        if not stage1.get('relevant'):
            return 'not_relevant_stage1'

        # Check stage 2
        if not stage2:
            return 'stage2_not_run'

        if stage2.get('rejected'):
            return 'not_relevant_stage2'

        # Success!
        return 'success'

    @staticmethod
    def print_summary(tasks: List[Dict[str, Any]], output_path: str, token_stats: Dict[str, Any] = None, compression_stats: Dict[str, Any] = None):
        """
        Print summary statistics.

        Args:
            tasks: List of processed tasks
            output_path: Path where results were written
            token_stats: Token usage statistics (optional)
            compression_stats: Compression statistics (optional)
        """
        # Filter out None tasks
        valid_tasks = [t for t in tasks if t]
        total = len(valid_tasks)

        if total == 0:
            print("\n⚠️ No tasks to summarize")
            return

        stage1_relevant = sum(1 for t in valid_tasks if (t.get('stage1_result') or {}).get('relevant'))
        stage1_not_relevant = total - stage1_relevant

        stage2_run = sum(1 for t in valid_tasks if t.get('stage2_result'))
        stage2_rejected = sum(1 for t in valid_tasks if (t.get('stage2_result') or {}).get('rejected'))
        letters_generated = sum(1 for t in valid_tasks
                                if (t.get('stage2_result') or {}).get('letter')
                                and not (t.get('stage2_result') or {}).get('rejected'))

        errors = sum(1 for t in valid_tasks if t.get('status') == 'failed')

        print("\n" + "="*80)
        print("📊 PROCESSING SUMMARY")
        print("="*80)
        print(f"\nTotal Leads Processed: {total}")
        print(f"\n🔍 Stage 1 - Classification:")
        print(f"  ✓ Relevant: {stage1_relevant} ({stage1_relevant/total*100:.1f}%)")
        print(f"  ✗ Not Relevant: {stage1_not_relevant} ({stage1_not_relevant/total*100:.1f}%)")

        if stage2_run > 0:
            print(f"\n✉️  Stage 2 - Letter Generation:")
            print(f"  ✓ Letters Generated: {letters_generated} ({letters_generated/total*100:.1f}%)")
            print(f"  ✗ Rejected (Stage 2): {stage2_rejected}")
            print(f"  ⚙️  Processed: {stage2_run}")

        if errors > 0:
            print(f"\n⚠️  Errors: {errors}")

        # Token usage summary
        if token_stats:
            print(f"\n💰 Token Usage & Cost:")
            total_tokens = token_stats['total_input'] + token_stats['total_output']
            print(f"  Total Tokens: {total_tokens:,} ({total_tokens/1000:.1f}K)")
            print(f"    - Input: {token_stats['total_input']:,}")
            print(f"    - Output: {token_stats['total_output']:,}")
            print(f"    - Cached: {token_stats['total_cached']:,} ({token_stats['total_cached']/max(1,token_stats['total_input'])*100:.1f}% of input)")
            print(f"\n  Stage 1 (Classification): {token_stats['stage1_input'] + token_stats['stage1_output']:,} tokens")
            print(f"  Stage 2 (Letter Gen): {token_stats['stage2_input'] + token_stats['stage2_output']:,} tokens")
            print(f"\n  💵 Total Cost: ${token_stats['total_cost_usd']:.3f}")
            if total > 0:
                print(f"  📊 Avg Cost per Lead: ${token_stats['total_cost_usd']/total:.4f}")

        # Compression summary
        if compression_stats and compression_stats['total_compressions'] > 0:
            print(f"\n🗜️  Context Compression:")
            print(f"  Total Compressions: {compression_stats['total_compressions']}")
            msgs_saved = compression_stats['total_messages_before'] - compression_stats['total_messages_after']
            print(f"  Messages Saved: {msgs_saved} ({compression_stats['total_messages_before']} → {compression_stats['total_messages_after']})")
            if compression_stats['total_messages_before'] > 0:
                reduction = (msgs_saved / compression_stats['total_messages_before']) * 100
                print(f"  Avg Reduction: {reduction:.1f}% per compression")

        print(f"\n💾 Results saved to: {output_path}")
        print("="*80 + "\n")
