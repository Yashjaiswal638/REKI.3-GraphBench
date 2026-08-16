# ═══════════════════════════════════════════════════
# Original AutoBench Prompt Templates
# ═══════════════════════════════════════════════════


CLASSIFY_PROMPT = """Please generate the verilog RTL code according to the following description and header information:
problem description:
{problem_description}
RTL header:
{dut_header}
please only reply verilog codes, no other words."""

SPEC_PROMPT = """1. Your task is to write a verilog testbench for an verilog RTL module code (we call it as "DUT", device under test). The infomation we have is the problem description that guides student to write the RTL code (DUT) and the header of the "DUT". Our target is to generate the verilog testbench for the DUT. This testbench can check if the DUT in verilog satisfies all technical requirements of the problem description.
2. You are in the first stage. In this stage, please summarize the technical details of the DUT and give me a technical specification of the testbench generation task, so we can use it to design its corresponding testbench.
3. The core of testbench is the testcases. It usually include two parts logically: the input signals to the DUT and the expected result signals from DUT. The testbench will send the input signals to DUT and check if the result signals are the same as the expected result signals. If they are the same, this means the DUT is passed. Otherwise the DUT fails.
4. Your technical specification should include these sections:
- section 1: specification of the DUT, including the module header of the RTL code. If table or other detailed data is provided in the original problem description, DO repeat them in your response. They are very important!!!
5. your response should be in the form of JSON.
6. below is the information including the problem description and the DUT header:
RTL circuit problem description:
{problem_description}
DUT header:
{dut_header}
your response must be in JSON form. example:
{{
  "circuit type": "...",
  "important data": "...",
  "technical specifications": ["...", "...", ...]
}}"""

SCENARIOS_PROMPT = """1. Your task is to write a verilog testbench for an verilog RTL module code (we call it as "DUT", device under test). The infomation we have is the problem description that guides student to write the RTL code (DUT) and the header of the "DUT". Our target is to generate the verilog testbench for the DUT. This testbench can check if the DUT in verilog satisfies all technical requirements of the problem description.
2. you are in section 2. in this section, please give me the test scenarios. you only need to describe the stimulus in each test scenarios. If time is important, please inform the clock cycle information. we will use the stimulus description to generate the test vectors and send them to DUT. you must not tell the expected results even though you know that.
3. your information is:
RTL circuit problem description:
{problem_description}
RTL testbench specification:
{spec}
DUT header:
{dut_header}
you only need to describe the stimulus in each test scenarios. If time is important, please inform the clock cycle information. we will use the stimulus description to generate the test vectors and send them to DUT. you must not tell the expected results even though you know that.
your response must be in JSON form. example:
{{
  "scenario 1": "...",
  "scenario 2": "...",
  "scenario 3": "..."
}}"""

RULES_PROMPT = """1. Your task is to write a verilog testbench for an verilog RTL module code (we call it as "DUT", device under test). The information we have is the problem description that guides student to write the RTL code (DUT) and the header of the "DUT". Our target is to generate the verilog testbench for the DUT. This testbench can check if the DUT in verilog satisfies all technical requirements of the problem description.
2. you are in section 3; in this section, please give me the rules of an ideal DUT. you should give these rules in python. (For convenience, you can use binary or hexadecimal format in python, i.e. 0b0010 and 0x1a). Later we will use these ideal rules to generate expected values in each test scenario. currently you must only generate the rules. the input of these rules should be related to the test vectors from test scenario. the rule should give the expected values under test vectors. You can use numpy, scipy or other third party python libraries to help you write the rules. Please import them if you need.
3. your information is:
RTL circuit problem description:
{problem_description}
RTL testbench specification:
{spec}
DUT header:
{dut_header}
test scenario: (please note the test vectors below, it will help you determine the input parameters of the rules)
{scenarios}
your response should only contain python code. For convenience, you can use binary or hexadecimal format in python. For example: 0b0010 and 0x1a"""

# CMB Driver (Stage4) — from script_pychecker_CMB.py
STAGE4_TXT1 = """
1. Your task is to write a verilog testbench for an verilog RTL module code (we call it as "DUT", device under test). The infomation we have is
- 1.1. the problem description that guides student to write the RTL code (DUT) and the header of the "DUT".
- 1.2. the module header.
- 1.3. the technical specification of testbench
- 1.4. test scenarios which determines value and sequential information of test vectors

2. you are in section 4. in this section, our target is to generate the verilog testbench for the DUT. This testbench can export the input and output signals of DUT at the important time points. The exported data will be send to a python script to check the correctness of DUT.
ATTENTION: The testbench does not need to check the DUT's output but only export the signals of DUT.
Instruction of saving signals to file:
(1) you should use $fopen and $fdisplay to export the important signals in testbench. the file name is "TBout.txt".
(2) When running testbench, for one time point, you should export 1 line. the example of the printed line is "%s"; If one scenario has multiple test cases, use letter suffix to represent different test cases, like "%s", "%s".
(3) Attention: before $fdisplay, you should always have a delay statement to make sure the signals are stable.
(4) the signals you save is the input and output of DUT, you should determine the signals according to DUT's header:
"""

STAGE4_TXT2 = """
The testbench does not need to check the DUT's output but only export the signals of DUT.
Instruction of saving signals to file:
(1) you should use $fopen and $fdisplay to export the important signals in testbench. the file name is "TBout.txt".
(2) When running testbench, for one time point, you should export 1 line. the example of the printed line is "%s"; If one scenario has multiple test cases, use letter suffix to represent different test cases, like "%s", "%s".
(3) Attention: before $fdisplay, you should always have a delay statement to make sure the signals are stable.
(4) the signals you save is the input and output of DUT, you should determine the signals according to DUT's header.
please only generate the verilog codes, no other words.
"""

# CMB Checker (Stage5) — from script_pychecker_CMB.py
STAGEPYGEN_PYFORMAT = """Your python scritp should contain a function "check_dut", its header is "def check_dut(test_vectors:list) -> bool:". It can also call other functions you write in this script. If all test scenarios passed, function "check_dut" should return an empty list [], otherwise it should return the list of failed scenarios indexes. You can use binary (like 0x1101), hexadecimal (like 0x1a) or normal number format in python."""

STAGEPYGEN_TXT1 = """
1. background: Your task is to verify the functional correctness of a verilog RTL module code (we call it as "DUT", device under test). Our plan is to first export the signals (input and output) of the DUT under test scenarios. Then, we will use a python script to check the correctness of DUT.
2. You are in the last stage. In this stage, we already export the signals of DUT. Your task is to write a python script. The python script contains one main function "check_dut" and other functions to be called by "check_dut" (this is optional). The input of "check_dut" is the signals of DUT in the format below: (the signal names are real, but the values are just for example)
%s
The main function "check_dut" should check the correctness according to the input signals. The input signals are all in decimal format. It will be called by other codes later.
3. %s
4. You have the information below to help you check the correctness of DUT:
"""

STAGEPYGEN_TXT2 = """
[IMPORTANT] %s
Optional: You can also use functions from numpy and scipy to help you check the correctness of DUT.
you can use binary (like 0b1011), hexadeciaml (like 0x1a) or normal number format in python for convenience.
please only generate the python codes, no other words.
"""

STAGEPYGEN_TAIL = """
def SignalTxt_to_dictlist(txt:str):
    lines = txt.strip().split("\\n")
    signals = []
    for line in lines:
        signal = {}
        line = line.strip().split(", ")
        for item in line:
            if "scenario" in item:
                item = item.split(": ")
                signal["scenario"] = item[1]
            else:
                item = item.split(" = ")
                key = item[0]
                value = item[1]
                if "x" not in value and "z" not in value:
                    signal[key] = int(value)
                else:
                    signal[key] = value
        signals.append(signal)
    return signals
with open("TBout.txt", "r") as f:
    txt = f.read()
vectors_in = SignalTxt_to_dictlist(txt)
tb_pass = check_dut(vectors_in)
print(tb_pass)
"""

# SEQ Driver (Stage4) — from script_pychecker_SEQ.py
STAGE4_SEQ_TXT1 = """
1. Your task is to complete a given verilog testbench code. This testbench is for a verilog RTL module code (we call it as "DUT", device under test). This circuit is a sequential circuit. The infomation we have is
- 1.1. the problem description that guides student to write the RTL code (DUT) and the header of the "DUT".
- 1.2. the module header.
- 1.3. test scenarios which determines values and sequential information of test vectors
- 1.4. the testbench structure
- 1.5. the instruction of writing our testbench
"""

STAGE4_SEQ_TXT2 = """
The testbench does not need to check the DUT's output but only export the signals of DUT. Please export the signals of DUT to a file named "TBout.txt" at the end of each scenario. The template is given below:
%s
The variables are already declared. The clock signal is already prepared. This output will be used to check the correctness of the DUT's output later.
please only use "#10" as the delay when you need. If you need longer delay, you can use multiple "#10", such as "#10; #10; #10;". Avoid meaningless long delay in your code.
If you need a loop in a scenario to check multiple time points, use "repeat" loop. for exmaple:
```
// scenario x
scenario = x;
signal_1 = 1;
repeat(5) begin
    %s
    #10;
end
```
Please determine the input signal's exact values according to given test scenarios.
Note: please complete the last initial code part (marked in the given testbench template). You should give me the completed full code. The testbench template above is to help you generate the code. You must use %%d when exporting values.
please generate the full testbench code. please only reply verilog codes, no other words.
"""

# SEQ Stage4b — from script_pychecker_SEQ.py
Stage4b_SEQ_TXT1 = """given the scenario based verilog testbench code below:"""

Stage4b_SEQ_TXT2 = """
please help me to export the input of DUT module by using code below:

[IMPORTANT]:
%s

you should insert the code above into scenario checking part. In each scenario, you should insert the code above after the input of DUT module changed. Don't delete the existing $display codes.

For example, for a circuit that has two input signals changed at different times in one scenario, the original code is like this:
- original code:
// scenario 1 begins
scenario = 1;
signal_1 = 1;
// insert $fdisplay here
#10;
signal_2 = 1;
// insert $fdisplay here
#10;
$fdisplay(file, "[check]scenario: %%d, signal_1 = %%d, signal_2 = %%d", scenario, signal_1, signal_2); // this should be reserved. Never change the existing codes.
#10;
// scenario 1 ends

- after insertion:
// scenario 1 begins
scenario = 1;
signal_1 = 1;
$fdisplay(file, "scenario: %%d, signal_1 = %%d, signal_2 = %%d", scenario, signal_1, signal_2);
#10;
signal_2 = 1;
$fdisplay(file, "scenario: %%d, signal_1 = %%d, signal_2 = %%d", scenario, signal_1, signal_2);
#10;
$fdisplay(file, "[check]scenario: %%d, signal_1 = %%d, signal_2 = %%d", scenario, signal_1, signal_2);
#10;
// scenario 1 ends

please insert codes according to the rules above. DO NOT modify other codes! please reply the modified full codes. please only reply verilog codes, no other words."""

# SEQ Checker (Stage5) — from script_pychecker_SEQ.py
STAGE5_SEQ_TXT1 = """
1. background: Your task is to verify the functional correctness of a verilog RTL module code (we call it as "DUT", device under test). This module is a sequential circuit. Our plan is to first export the signals (input and output) of the DUT under test scenarios. Then, we will use a python script to check the correctness of DUT.
2. You are in stage 5. In this stage, we already exported the signals of DUT. The signals are like below: (the signal names are real, but the values are just for example, clock signals are not included, each vector represents a new clock cycle)
%s
Here's the explanation of some special signals in signal vectors:
- "scenario": The "scenario" is not DUT's signal but to tell you the current scenario index.
- "check_en": The "check_en" signal is not from the DUT. "Check_en" is a bool value to tell you this is the time to check the output of DUT. It is related to the class method "check" (we will explain it later). After checking the output, a new scenario will start.
3. Your current task is: write a python class "GoldenDUT". This python class can represent the golden DUT (the ideal one). In your "GoldenDUT", you should do the following things:
- 3.1. write a method "def __init__(self)". Set the inner states/values of the golden DUT. These values have suffix "_reg". The initial value of these inner values is "x", but later will be digits. The "__init__" method has no input parameters except "self".
- 3.2. write a method "def load(self, signal_vector)". This method is to load the important input signals and the inner values of "GoldenDUT" shall change according to the input signals. There is no clock signal in the input signal vector, every time the "load" method is called, it means a new clock cycle. The initial values "x" should be changed according to the input signals. This method has no return value.
- 3.3. write a method "def check(self, signal_vector)". This method is to determine the expected output values and compare them with output signals from DUT. It should return True or False only. If return false, please print the error message. Hint: you can use code like "print(f"Scenario: {signal_vector['scenario']}, expected: a={a_reg}, observed a={a_observed}")" to print, suppose "a" is the output signal's name.
- 3.4. write other methods you need, they can be called by "load" or "check".
- 3.5. the input of "load" and "check" is the signal vector. The signal vector is a dictionary, the key is the signal name, the value is the signal value.
4. Other information:
- You can use binary (like 0x1101), hexadecimal (like 0x1a) or normal number format in python.
- if the bit width of one variable is limited, use bit mask to assure the correctness of the value.
- you can import numpy, math, scipy or other python libraries to help you write the python class.
5. You have the information below to help you check the correctness of DUT:
"""

STAGE5_SEQ_TXT2 = """
[IMPORTANT]
I will repeat the important information:
3. Your current task is: write a python class "GoldenDUT". This python class can represent the golden DUT (the ideal one). In your "GoldenDUT", you should do the following things:
- 3.1. write a method "def __init__(self)". Set the inner states/values of the golden DUT. These values have suffix "_reg". The initial value of these inner values should be digits. You can set the initial values according to information or just "0"s. The "__init__" method has no input parameters except "self".
- 3.2. write a method "def load(self, signal_vector)". This method is to load the important input signals and the inner values of "GoldenDUT" shall change according to the input signals. There is no clock signal in the input signal vector, every time the "load" method is called, it means a new clock cycle. The initial values "x" should be changed according to the input signals. This method has no return value.
- 3.3. write a method "def check(self, signal_vector)". This method is to determine the expected output values and compare them with output signals from DUT. It should return True or False only. If return false, please print the error message. Hint: you can use code like "print(f"Scenario: {signal_vector['scenario']}, expected: a={a_reg}, observed a={a_observed}")" to print, suppose "a" is the output signal's name.
- 3.4. write other methods you need, they can be called by "load" or "check".
- 3.5. the input of "load" and "check" is the signal vector. The signal vector is a dictionary, the key is the signal name, the value is the signal value.
4. Other information:
- You can use binary (like 0x1101), hexadecimal (like 0x1a) or normal number format in python.
- if the bit width of one variable is limited, use bit mask to assure the correctness of the value.
- you can import numpy, math, scipy or other python libraries to help you write the python class.

please only reply the python codes of the python class. no other words.
"""

STAGE5_SEQ_CODE1 = """
def check_dut(vectors_in):
    golden_dut = GoldenDUT()
    failed_scenarios = []
    for vector in vectors_in:
        if vector["check_en"]:
            check_pass = golden_dut.check(vector)
            if check_pass:
                print(f"Passed; vector: {vector}")
            else:
                print(f"Failed; vector: {vector}")
                failed_scenarios.append(vector["scenario"])
        golden_dut.load(vector)
    return failed_scenarios
"""

STAGE5_SEQ_CODE2 = """
def SignalTxt_to_dictlist(txt:str):
    signals = []
    lines = txt.strip().split("\\n")
    for line in lines:
        signal = {}
        if line.startswith("[check]"):
            signal["check_en"] = True
            line = line[7:]
        elif line.startswith("scenario"):
            signal["check_en"] = False
        else:
            continue
        line = line.strip().split(", ")
        for item in line:
            if "scenario" in item:
                item = item.split(": ")
                signal["scenario"] = item[1].replace(" ", "")
            else:
                item = item.split(" = ")
                key = item[0]
                value = item[1]
                if ("x" not in value) and ("X" not in value) and ("z" not in value):
                    signal[key] = int(value)
                else:
                    if ("x" in value) or ("X" in value):
                        signal[key] = 0
                    else:
                        signal[key] = 0
        signals.append(signal)
    return signals
with open("TBout.txt", "r") as f:
    txt = f.read()
vectors_in = SignalTxt_to_dictlist(txt)
tb_pass = check_dut(vectors_in)
print(tb_pass)
"""

DEBUG_PROMPT = """please fix the verilog testbench code below according to the error message below. please directly give me the corrected verilog testbench codes.
Attention: never remove the irrelevant codes!!!
your verilog testbench should be like:
```verilog
`timescale 1ns / 1ps
(more verilog testbench code here...)
endmodule
```
please only reply the full code modified. NEVER remove other irrelevant codes!!!
The testbench I give you is the one with error. To be convienient, each of the line begins with a line number. The line number also appears at the error message. You should use the line number to locate the error with the help of error message.

previous testbench with error:
{driver_code}

compiling error message:
{sim_error}"""