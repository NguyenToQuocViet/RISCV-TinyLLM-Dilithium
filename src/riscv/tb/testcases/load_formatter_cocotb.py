#------------------------------------------------------------------------------
# Module      : load_formatter_cocotb
# Description : Directed checks for load-lane selection and extension.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-23
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import Timer

async def direct_check(
    dut,
    read_data,
    effective_address,
    mem_type,
    expected_result,
):
    dut.read_data.value         = read_data
    dut.effective_address.value = effective_address
    dut.mem_type.value          = mem_type

    await Timer(1, unit="ns")

    load_result = int(dut.load_result.value)

    assert load_result == expected_result, (
        f"Load result: Expected 0x{expected_result:08X}, Got 0x{load_result:08X}; "
        f"read_data=0x{read_data:08X}, address=0x{effective_address:08X}, "
        f"mem_type={mem_type:03b}"
    )

@cocotb.test()
async def test_byte_formatting(dut):
    #select each byte from a word with distinct lanes
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0000,
        mem_type=0,
        expected_result=0xFFFF_FFEF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0001,
        mem_type=0,
        expected_result=0xFFFF_FFBE,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0002,
        mem_type=0,
        expected_result=0xFFFF_FFAD,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0003,
        mem_type=0,
        expected_result=0xFFFF_FFDE,
    )

    #address+4
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0004,
        mem_type=0,
        expected_result=0xFFFF_FFEF,
    )

    #test 00, 7F, 80 and FF across different byte lanes and addresses
    await direct_check(
        dut,
        read_data=0x1234_5600,
        effective_address=0x19A7_42C0,
        mem_type=0,
        expected_result=0x0000_0000,
    )

    await direct_check(
        dut,
        read_data=0x1234_7F78,
        effective_address=0xC407_EB19,
        mem_type=0,
        expected_result=0x0000_007F,
    )

    await direct_check(
        dut,
        read_data=0x1280_5678,
        effective_address=0x07DC_F526,
        mem_type=0,
        expected_result=0xFFFF_FF80,
    )

    await direct_check(
        dut,
        read_data=0xFF34_5678,
        effective_address=0x4F10_CAE7,
        mem_type=0,
        expected_result=0xFFFF_FFFF,
    )


    #address boundaries: upper address bits do not affect byte selection
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0000_0000,
        mem_type=0,
        expected_result=0xFFFF_FFEF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0xFFFF_FFFF,
        mem_type=0,
        expected_result=0xFFFF_FFDE,
    )


@cocotb.test()
async def test_halfword_formatting(dut):
    #test choosing lower and upper halfword
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x19A7_42C0,
        mem_type=1,
        expected_result=0xFFFF_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0xE035_6B96,
        mem_type=1,
        expected_result=0xFFFF_DEAD,
    )

    #test 0000, 7FFF, 8000 and FFFF across both halfword lanes and different addresses
    await direct_check(
        dut,
        read_data=0x1234_0000,
        effective_address=0x724C_DA38,
        mem_type=1,
        expected_result=0x0000_0000,
    )

    await direct_check(
        dut,
        read_data=0x1234_8000,
        effective_address=0x3D92_71A4,
        mem_type=1,
        expected_result=0xFFFF_8000,
    )

    await direct_check(
        dut,
        read_data=0x7FFF_5678,
        effective_address=0x91B5_0C72,
        mem_type=1,
        expected_result=0x0000_7FFF,
    )

    await direct_check(
        dut,
        read_data=0xFFFF_5678,
        effective_address=0xB249_187A,
        mem_type=1,
        expected_result=0xFFFF_FFFF,
    )


    #test address boundaries
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0000_0000,
        mem_type=1,
        expected_result=0xFFFF_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0xFFFF_FFFC,
        mem_type=1,
        expected_result=0xFFFF_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0xFFFF_FFFE,
        mem_type=1,
        expected_result=0xFFFF_DEAD,
    )


@cocotb.test()
async def test_word_formatting(dut):
    #test full word data at different aligned addresses
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x07DC_F524,
        mem_type=2,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0x1234_5678,
        effective_address=0xF631_8BCC,
        mem_type=2,
        expected_result=0x1234_5678,
    )

    #test zero and all-one data
    await direct_check(
        dut,
        read_data=0x0000_0000,
        effective_address=0x2CA8_D150,
        mem_type=2,
        expected_result=0x0000_0000,
    )

    await direct_check(
        dut,
        read_data=0xFFFF_FFFF,
        effective_address=0xD785_406C,
        mem_type=2,
        expected_result=0xFFFF_FFFF,
    )

    #test bit 31 boundaries
    await direct_check(
        dut,
        read_data=0x7FFF_FFFF,
        effective_address=0x83BE_9728,
        mem_type=2,
        expected_result=0x7FFF_FFFF,
    )

    await direct_check(
        dut,
        read_data=0x8000_0000,
        effective_address=0x4F10_CAE4,
        mem_type=2,
        expected_result=0x8000_0000,
    )

    #test address boundaries
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0000_0000,
        mem_type=2,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0x1234_5678,
        effective_address=0xFFFF_FFFC,
        mem_type=2,
        expected_result=0x1234_5678,
    )


@cocotb.test()
async def test_unsigned_byte_formatting(dut):
    #select each byte from a word with distinct lanes
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0000,
        mem_type=4,
        expected_result=0x0000_00EF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0001,
        mem_type=4,
        expected_result=0x0000_00BE,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0002,
        mem_type=4,
        expected_result=0x0000_00AD,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0003,
        mem_type=4,
        expected_result=0x0000_00DE,
    )

    #address+4
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0001_0004,
        mem_type=4,
        expected_result=0x0000_00EF,
    )

    #test 00, 7F, 80 and FF across different byte lanes and addresses
    await direct_check(
        dut,
        read_data=0x1234_5600,
        effective_address=0x19A7_42C0,
        mem_type=4,
        expected_result=0x0000_0000,
    )

    await direct_check(
        dut,
        read_data=0x1234_7F78,
        effective_address=0xC407_EB19,
        mem_type=4,
        expected_result=0x0000_007F,
    )

    await direct_check(
        dut,
        read_data=0x1280_5678,
        effective_address=0x07DC_F526,
        mem_type=4,
        expected_result=0x0000_0080,
    )

    await direct_check(
        dut,
        read_data=0xFF34_5678,
        effective_address=0x4F10_CAE7,
        mem_type=4,
        expected_result=0x0000_00FF,
    )


    #address boundaries: upper address bits do not affect byte selection
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0000_0000,
        mem_type=4,
        expected_result=0x0000_00EF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0xFFFF_FFFF,
        mem_type=4,
        expected_result=0x0000_00DE,
    )


@cocotb.test()
async def test_unsigned_halfword_formatting(dut):
    #test choosing lower and upper halfword
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x19A7_42C0,
        mem_type=5,
        expected_result=0x0000_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0xE035_6B96,
        mem_type=5,
        expected_result=0x0000_DEAD,
    )

    #test 0000, 7FFF, 8000 and FFFF across both halfword lanes and different addresses
    await direct_check(
        dut,
        read_data=0x1234_0000,
        effective_address=0x724C_DA38,
        mem_type=5,
        expected_result=0x0000_0000,
    )

    await direct_check(
        dut,
        read_data=0x1234_8000,
        effective_address=0x3D92_71A4,
        mem_type=5,
        expected_result=0x0000_8000,
    )

    await direct_check(
        dut,
        read_data=0x7FFF_5678,
        effective_address=0x91B5_0C72,
        mem_type=5,
        expected_result=0x0000_7FFF,
    )

    await direct_check(
        dut,
        read_data=0xFFFF_5678,
        effective_address=0xB249_187A,
        mem_type=5,
        expected_result=0x0000_FFFF,
    )


    #test address boundaries
    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0x0000_0000,
        mem_type=5,
        expected_result=0x0000_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0xFFFF_FFFC,
        mem_type=5,
        expected_result=0x0000_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xDEAD_BEEF,
        effective_address=0xFFFF_FFFE,
        mem_type=5,
        expected_result=0x0000_DEAD,
    )


@cocotb.test()
async def test_reserved_mem_type(dut):
    #test reserved code 011 at all four offsets
    await direct_check(
        dut,
        read_data=0x0000_0000,
        effective_address=0x19A7_42C0,
        mem_type=3,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xFFFF_FFFF,
        effective_address=0xE035_6B95,
        mem_type=3,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0x1234_5678,
        effective_address=0x724C_DA3A,
        mem_type=3,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xA5A5_5A5A,
        effective_address=0xA86F_103F,
        mem_type=3,
        expected_result=0xDEAD_BEEF,
    )

    #test reserved code 110 at all four offsets
    await direct_check(
        dut,
        read_data=0x0000_0000,
        effective_address=0x3D92_71A4,
        mem_type=6,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xFFFF_FFFF,
        effective_address=0xC407_EB19,
        mem_type=6,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0x1234_5678,
        effective_address=0x6AF0_932E,
        mem_type=6,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xA5A5_5A5A,
        effective_address=0x91B5_0C73,
        mem_type=6,
        expected_result=0xDEAD_BEEF,
    )

    #test reserved code 111 at all four offsets
    await direct_check(
        dut,
        read_data=0x0000_0000,
        effective_address=0x58E3_A6D0,
        mem_type=7,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xFFFF_FFFF,
        effective_address=0xB249_1879,
        mem_type=7,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0x1234_5678,
        effective_address=0x07DC_F526,
        mem_type=7,
        expected_result=0xDEAD_BEEF,
    )

    await direct_check(
        dut,
        read_data=0xA5A5_5A5A,
        effective_address=0xF631_8BCF,
        mem_type=7,
        expected_result=0xDEAD_BEEF,
    )
