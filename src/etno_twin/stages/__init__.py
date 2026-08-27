"""Pipeline stages.

Each stage is a module exposing a pure ``run(...)`` that reads declared artifacts and
writes declared artifacts, plus its own entry point so the orchestrator can invoke it as
a process.

**Stages do not import each other.** They meet only through files whose schema is
declared in `etno_twin.kernel.schemas`, and an import-linter contract enforces the
independence rather than trusting it. That is the property ADR-0001 is choosing between
architectural styles over, so the tracer bullet has to demonstrate it, not assume it: a
chain that passed data frames from one function to the next inside a single process would
run just as well and would validate nothing.

This module stays empty on purpose. Re-exporting the stages here would make importing the
package pull in the training stage, and with it PyTorch — turning every invocation of the
cheapest stage into a several-second import and quietly coupling the core to a dependency
it is supposed to survive without.
"""
