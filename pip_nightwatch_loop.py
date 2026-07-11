import time
import os
import random
from pathlib import Path
import pip_config
import pip_platform
from pip_goal_engine import PipGoalEngine

def get_random_brain_file():
    # Looks for random files in the main brain folder to learn from
    brain_dir = pip_platform.BRAIN_ROOT
    if not brain_dir.exists():
        return None
        
    txt_files = list(brain_dir.glob("*.txt"))
    if not txt_files:
        return None
        
    return random.choice(txt_files)

def run_sleep_cycle():
    if os.environ.get("PIP_ENABLE_NIGHTWATCH") != "1":
        print("Nightwatch is disabled. Set PIP_ENABLE_NIGHTWATCH=1 to run the unattended loop.")
        return

    print("Pip Nightwatch Mode Initiated...")
    engine = PipGoalEngine(max_steps=5)
    
    # Import embedding tool
    import pip_embeddings
    import pip_config
    import pip_self_reflection

    # Import phone sync and messenger
    try:
        import pip_phone_sync
        _phone_sync_available = True
        print("[nightwatch] Phone sync watcher enabled.")
    except ImportError:
        _phone_sync_available = False

    try:
        import pip_messenger
        _messenger_available = pip_messenger.is_enabled()
        if _messenger_available:
            print("[nightwatch] Messenger enabled — Pip can notify you.")
        else:
            print("[nightwatch] Messenger module found but disabled in pip_secrets.json.")
    except ImportError:
        _messenger_available = False

    memory_store = pip_embeddings.PersonaMemoryStore()
    
    while True:
        try:
            import pip_bos
            bos_phase = pip_bos.get_phase()
        except ImportError:
            bos_phase = "BUILD"
            
        # 0. Phone Sync — check drop folder for new telemetry files (UNGATED)
        if _phone_sync_available:
            try:
                results = pip_phone_sync.run_sync()
                for r in results:
                    if r.get("ok"):
                        print(f"[nightwatch] Phone sync: {r['file']} — {r.get('event_count', 0)} events ingested.")
                    else:
                        print(f"[nightwatch] Phone sync failed: {r['file']} — {r.get('error', 'unknown')}")
            except Exception as e:
                print(f"[nightwatch] Phone sync error: {e}")

        # 0.5 Mailbox Sync — check Claude's mailbox for unread replies (UNGATED)
        try:
            import sys
            mailbox_dir = str(pip_platform.BRAIN_ROOT / "01_agent_context" / "pip_mailbox")
            if mailbox_dir not in sys.path:
                sys.path.insert(0, mailbox_dir)
            import claude_mailbox
            
            unread = claude_mailbox.unread()
            if unread:
                print(f"[nightwatch] Found {len(unread)} unread messages from Claude.")
                if _messenger_available:
                    for msg in unread:
                        title = f"Claude Reply ({msg.get('id', '?')})"
                        body = msg.get("text", "")
                        pip_messenger.notify(title, body)
                else:
                    print("[nightwatch] Messenger unavailable. Could not relay Claude's messages.")
        except Exception as e:
            print(f"[nightwatch] Mailbox sync error: {e}")
            
        # BOS GATING FOR HEAVY TASKS
        if bos_phase in ["DWELL", "SHED"]:
            print(f"[nightwatch] BOS Phase is {bos_phase}. System under stress. Yielding (sleeping)...")
            time.sleep(300)
            continue
            
        skip_heavy = (bos_phase == "AUDIT")
        if skip_heavy:
            print(f"[nightwatch] BOS Phase is AUDIT. Skipping heavy background jobs.")

        # 1. Self-Reflection
        pip_self_reflection.run_reflection_cycle()
        
        # 2. Dream Cycle
        if not skip_heavy:
            target_file = get_random_brain_file()
            if target_file:
                print(f"Pip is dreaming about {target_file.name}...")
                dream_name = f"dream_{target_file.stem[:10]}.txt"
                goal = f"""You are in a sleep cycle (free play research).
Please read the file named "{target_file.name}" from the brain.
Then, write a short 1-2 sentence core truth or belief of what you learned into your own memory folder as a new file called "{dream_name}".
When you are done, use finish_goal.
"""
                try:
                    result = engine.run_goal(goal, yield_logs=True)
                    print(f"Dream cycle finished. Result: {result}")
                    
                    # RAG Integration: Embed the newly created dream
                    mem_path = pip_config.get_memory_path() / dream_name
                    if mem_path.exists():
                        dream_text = mem_path.read_text(encoding="utf-8").strip()
                        if dream_text:
                            print(f"Embedding dream into Persona Memory: {dream_text[:50]}...")
                            memory_store.add_memory(dream_text)
                    
                except Exception as e:
                    print(f"Dream cycle failed: {e}")
                
        # 3. Parameter Sweep
        print("Running parameter tuning sweep...")
        try:
            import pip_eval
            sweep_result = pip_eval.sweep_parameters()
            if sweep_result.get("proposed_change"):
                print("Sweep found a better parameter configuration. Check permissions queue.")
                # Notify owner about parameter change proposal
                if _messenger_available:
                    try:
                        pip_messenger.notify(
                            "Parameter Sweep Result",
                            f"Pip found a potentially better configuration during her sleep cycle. "
                            f"Check the permissions queue in the dashboard to review.",
                        )
                    except Exception:
                        pass
        except Exception as e:
            print(f"Sweep failed: {e}")
            
        # 4. Night School
        if not skip_heavy:
            # Run Night School once a day. For simplicity, we just check if it's been 24 hours.
            import datetime
            now = datetime.datetime.now()
            
            # We can store the last run time in a simple file
            last_school_file = pip_config.get_memory_path() / "last_night_school.txt"
            last_school_date = None
            if last_school_file.exists():
                last_school_date = last_school_file.read_text(encoding="utf-8").strip()
                
            current_date = now.strftime("%Y-%m-%d")
            
            if last_school_date != current_date:
                print(f"[nightwatch] Initiating Night School for {current_date}...")
                try:
                    import pip_night_school
                    pip_night_school.run_night_school()
                    last_school_file.write_text(current_date, encoding="utf-8")
                except Exception as e:
                    print(f"[nightwatch] Night School failed: {e}")

        # 5. GitHub Scout - once a day, scan GitHub for relevant recent builds
        #    and drop a digest into Claude's @CLAUDE handoff queue.
        last_scout_file = pip_config.get_memory_path() / "last_github_scout.txt"
        last_scout_date = last_scout_file.read_text(encoding="utf-8").strip() \
            if last_scout_file.exists() else None
        if last_scout_date != current_date:
            print(f"[nightwatch] Running GitHub Scout for {current_date}...")
            try:
                import pip_github_scout
                pip_github_scout.run_scout()
                last_scout_file.write_text(current_date, encoding="utf-8")
            except Exception as e:
                print(f"[nightwatch] GitHub Scout failed: {e}")

        # 6. Daily Lesson Compilation
        last_lesson_id_file = pip_config.get_memory_path() / "last_lesson_id.txt"
        last_lesson_id = last_lesson_id_file.read_text(encoding="utf-8").strip() if last_lesson_id_file.exists() else None
        
        try:
            import sys
            smart_dir = str(pip_platform.BRAIN_ROOT / "02_pip_and_system_architecture" / "builds" / "work_smart")
            if smart_dir not in sys.path:
                sys.path.insert(0, smart_dir)
            import lessons
            
            all_lessons = lessons._all()
            new_lessons = []
            
            # Extract only the lessons that occurred after the last_lesson_id
            for L in reversed(all_lessons):
                if L.get("id") == last_lesson_id:
                    break
                new_lessons.insert(0, L)
                
            if new_lessons:
                print(f"[nightwatch] Compiling {len(new_lessons)} new daily lessons...")
                import json
                handoff_dir = pip_platform.BRAIN_ROOT / "01_agent_context" / "handoffs"
                handoff_dir.mkdir(parents=True, exist_ok=True)
                stamp = now.strftime("%Y-%m-%d_%H%M%S")
                fp = handoff_dir / f"@CLAUDE_daily_lessons_{stamp}.md"
                
                content = f"# Daily Lesson Compilation ({current_date})\n\n"
                content += "Please review Pip's caught mistakes and lessons to ensure they are integrated into our practices:\n\n"
                for L in new_lessons:
                    content += f"## {L.get('topic', 'Unknown Topic')}\n- **What happened:** {L.get('what_happened', 'N/A')}\n- **Lesson:** {L.get('lesson', 'N/A')}\n\n"
                    
                fp.write_text(content, encoding="utf-8")
                
                # Update watermark
                latest_id = new_lessons[-1].get("id")
                if latest_id:
                    last_lesson_id_file.write_text(latest_id, encoding="utf-8")
                    
                print(f"[nightwatch] Daily lesson compilation saved to {fp.name}")
            else:
                print("[nightwatch] No new lessons to compile.")
        except Exception as e:
            print(f"[nightwatch] Daily lesson compilation failed: {e}")

        # Sleep for a long time before next dream (e.g. 15 minutes)
        time.sleep(900)

if __name__ == "__main__":
    run_sleep_cycle()

