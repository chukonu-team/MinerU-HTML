"""
LLM inference utilities for structured generation.

This module provides functions to generate structured outputs using vLLM
with optional state machine-based logits processing.
"""

import copy
from typing import Union

from vllm import SamplingParams

from dripper.base import (DripperGenerateInput, DripperGenerateOutput,
                          check_and_find_max_item_id)
from dripper.exceptions import DripperTypeError
from dripper.inference.imp import InferenceBackend
from dripper.inference.logits import build_token_state_machine
import asyncio


def generate(
    llm: InferenceBackend,
    input: Union[DripperGenerateInput, list[DripperGenerateInput], str, list[str]],
    use_state_machine: str = 'v1',
) -> list[DripperGenerateOutput]:
    """
    Generate structured outputs using vLLM with optional state machine.

    Performs batch inference on input data, optionally using a state machine
    to guide token generation for structured JSON output.

    Args:
        llm: LLM instance for inference, should be a specific type in practical cases.
        input: Input data in various formats:
               - Single DripperGenerateInput
               - List of DripperGenerateInput
               - Single HTML string (will be converted to DripperGenerateInput)
               - List of HTML strings
        use_state_machine: State machine version to use ('v1', 'v2', or None/'' to disable)

    Returns:
        List of DripperGenerateOutput objects containing generated responses

    Raises:
        DripperTypeError: If input type is not supported
    """
    # Normalize input to list of DripperGenerateInput
    sampling_params_list = []
    base_gen_config = SamplingParams(
        top_k=1, top_p=0.95, temperature=0, max_tokens=8 * 1024
    )
    if isinstance(input, list):
        input_list = []
        for p in input:
            if isinstance(p, str):
                # Convert string to DripperGenerateInput with identity prompt
                di = DripperGenerateInput(alg_html=p, prompt=lambda x: x)
                input_list.append(di)
                temp_gen_config = SamplingParams(top_k=1, top_p=0.95, temperature=0, max_tokens=(8 * di.max_item_id+10))
                sampling_params_list.append(temp_gen_config)
            elif isinstance(p, DripperGenerateInput):
                input_list.append(p)
                temp_gen_config = SamplingParams(top_k=1, top_p=0.95, temperature=0, max_tokens=(8 * p.max_item_id+10))
                sampling_params_list.append(temp_gen_config)
            else:
                raise DripperTypeError(
                    f'Unsupported input type: {type(p)}, {p}'
                )
            
    elif isinstance(input, str):
        # Convert single string to list
        di = DripperGenerateInput(alg_html=input, prompt=lambda x: x)
        input_list = [di]
        sampling_params_list.append(SamplingParams(top_k=1, top_p=0.95, temperature=0, max_tokens=(8 * di.max_item_id+10)))
    elif isinstance(input, DripperGenerateInput):
        # Convert single DripperGenerateInput to list
        input_list = [input]
        sampling_params_list.append(SamplingParams(top_k=1, top_p=0.95, temperature=0, max_tokens=(8 * input.max_item_id+10)))
    else:
        raise DripperTypeError(
            f'Unsupported input type: {type(input)}, {input}'
        )

    # Extract prompts from input data
    prompt_list = [data.full_prompt for data in input_list]
    # Base generation configuration


    if use_state_machine:
        # If use_state_machine is not None or empty string
        # Set state machine to sampling_params_arg
        state_machines = [
            build_token_state_machine(
                check_and_find_max_item_id(data.alg_html),
                llm.get_tokenizer(),
                version=use_state_machine,
            )
            for data in input_list
        ]
        sampling_params_arg = []
        for state_machine in state_machines:
            # Create a copy of base config and add logits processor
            sampling_params = copy.deepcopy(base_gen_config)
            sampling_params.logits_processors = [state_machine.process_logit]
            sampling_params_arg.append(sampling_params)
    else:
        # If use_state_machine is None or empty string
        # Use base_gen_config without logits processors
        sampling_params_arg = base_gen_config
    # Perform batch generation
    res_list = llm.generate(prompt_list, sampling_params_list)

    # Convert results to DripperGenerateOutput objects
    output_list = []
    for input_data, res_data in zip(input_list, res_list):
        case_id = input_data.case_id
        output_list.append(
            DripperGenerateOutput(
                case_id=case_id, response=res_data.outputs[0].text
            )
        )
    return output_list


async def generateAsync(
    llm: InferenceBackend,
    # input: Union[DripperGenerateInput, list[DripperGenerateInput], str, list[str]],
    input: Union[DripperGenerateInput, str], # only support single input for async
    use_state_machine: str = 'v1',
) -> list[DripperGenerateOutput]:
    """
    Generate structured outputs using vLLM with optional state machine.

    Performs batch inference on input data, optionally using a state machine
    to guide token generation for structured JSON output.

    Args:
        llm: LLM instance for inference, should be a specific type in practical cases.
        input: Input data in various formats:
               - Single DripperGenerateInput
               - List of DripperGenerateInput
               - Single HTML string (will be converted to DripperGenerateInput)
               - List of HTML strings
        use_state_machine: State machine version to use ('v1', 'v2', or None/'' to disable)

    Returns:
        List of DripperGenerateOutput objects containing generated responses

    Raises:
        DripperTypeError: If input type is not supported
    """
    # Normalize input to list of DripperGenerateInput
    sampling_params_list = []
    base_gen_config = SamplingParams(
        top_k=1, top_p=0.95, temperature=0, max_tokens=8 * 1024
    )
    if isinstance(input, list):
        input_list = []
        for p in input:
            if isinstance(p, str):
                # Convert string to DripperGenerateInput with identity prompt
                di = DripperGenerateInput(alg_html=p, prompt=lambda x: x)
                input_list.append(di)
                temp_gen_config = SamplingParams(top_k=1, top_p=0.95, temperature=0, max_tokens=(8 * di.max_item_id+10))
                sampling_params_list.append(temp_gen_config)
            elif isinstance(p, DripperGenerateInput):
                input_list.append(p)
                temp_gen_config = SamplingParams(top_k=1, top_p=0.95, temperature=0, max_tokens=(8 * p.max_item_id+10))
                sampling_params_list.append(temp_gen_config)
            else:
                raise DripperTypeError(
                    f'Unsupported input type: {type(p)}, {p}'
                )
            
    elif isinstance(input, str):
        # Convert single string to list
        di = DripperGenerateInput(alg_html=input, prompt=lambda x: x)
        input_list = [di]
        sampling_params_list.append(SamplingParams(top_k=1, top_p=0.95, temperature=0, max_tokens=(8 * di.max_item_id+10)))
    elif isinstance(input, DripperGenerateInput):
        # Convert single DripperGenerateInput to list
        input_list = [input]
        sampling_params_list.append(SamplingParams(top_k=1, top_p=0.95, temperature=0, max_tokens=(8 * input.max_item_id+10)))
    else:
        raise DripperTypeError(
            f'Unsupported input type: {type(input)}, {input}'
        )

    # Extract prompts from input data
    prompt_list = [data.full_prompt for data in input_list]
    # Base generation configuration


    if use_state_machine:
        # If use_state_machine is not None or empty string
        # Set state machine to sampling_params_arg
        state_machines = [
            build_token_state_machine(
                check_and_find_max_item_id(data.alg_html),
                llm.get_tokenizer(),
                version=use_state_machine,
            )
            for data in input_list
        ]
        sampling_params_arg = []
        for state_machine in state_machines:
            # Create a copy of base config and add logits processor
            sampling_params = copy.deepcopy(base_gen_config)
            sampling_params.logits_processors = [state_machine.process_logit]
            sampling_params_arg.append(sampling_params)
    else:
        # If use_state_machine is None or empty string
        # Use base_gen_config without logits processors
        sampling_params_arg = base_gen_config
    # Perform batch generation
    res_list = await llm.generateAsync(prompt_list, sampling_params_list[0])

    # Convert results to DripperGenerateOutput objects
    output_list = []
    for input_data, res_data in zip(input_list, res_list):
        case_id = input_data.case_id
        output_list.append(
            DripperGenerateOutput(
                case_id=case_id, response=res_data.outputs[0].text
            )
        )
    return output_list
