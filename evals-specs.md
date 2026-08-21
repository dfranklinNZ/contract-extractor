
The outcome of this is to create the start of a reusable eval capability, which I can copy out into new projects and extend.

My main goal is learning and understanding this eval and agent capability.

I am junior at python, so I want it to be as easy to understand as possible 

I want easy to understand EVAL “building blocks” for some stages types of EVALS in the evals Python package. Examples with project specific implementation:
- Exact-match gradable: governing law (a jurisdiction string), effective date (a date). Right or wrong, deterministically checkable.
- Fuzzy / LLM judgment gradable: termination clause, liability cap summary. "Correct" is a spectrum; needs an LLM-judge or human.
- Set-gradable: parties (a list — needs precision/recall, not a single match).

I want to run a golden set of data (in this case evals/data) through my pipeline, and save the results to a database say eval_contracts.db

I want to create and select the tasks (say tasks.yaml) for running the eval - for this project, i think one task = one contract
For each of the 6 fields on the contract in gold dataset, this would compare contract_id, field_name, correct_value, acceptable_alternatives, source_page - not sure if this is best covered in tasks.yaml or reference.json or elsewhere

I want any system prompt, judge prompt, tool or anything else that might enter agent context to be versioned, so that differences can be tracked for experiments. And when hill-climbing, i can hypothesis and change a single variable and see the impact on the eval result

LLM judge to output a verdit (correct/partial/wrong), reasoning, confidence

Then i want the outcomes saved in a database (still just use sqlite) 

Next i want a simple webpage in the project, that when opened shows this data - and shows the different runs along with key metadata. The aim to be able visibly hill climb or see regression, and understand why. Metadata such as:
- Model + other settings like effort
- Tools and tool versions
- Skills and skill versions
- Capture the model reasoning / chain of thoughts for the session

