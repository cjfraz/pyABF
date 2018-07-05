"""
Code here relates to reading epoch information from ABF files and synthesizing
analog and digital waveforms to represent command signals.
"""

import warnings
import numpy as np


class Epochs:
    def __init__(self, abf, channel):
        """
        handles epoch values for a single sweep/channel
        """

        self.abf = abf
        self.channel = channel

        self._initEpochVars()

        if abf.abfFileFormat == 1:
            self._updateForABFv1()
        elif abf.abfFileFormat == 2:
            self._addPreEpoch()
            self._fillEpochsFromABF()
            self._addPostEpoch()

        self._createEpochLabels()
        self._updateEpochDetails()

    def __len__(self):
        return len(self.epochList)

    def __str__(self):
        msg = f"Channel {self.channel} epochs ({self.epochCount}): "
        msg += ", ".join(self.label)
        return msg

    def __repr__(self):
        return "ChannelEpochs(ABF, %s)" % (self.channel)

    def _initEpochVars(self):
        """
        Create empty lists for every field of the waveform editor
        """
        self.pointStart = []
        self.pointEnd = []
        self.label = []
        self.type = []
        self.level = []
        self.levelDelta = []
        self.duration = []
        self.durationDelta = []
        self.pulsePeriod = []
        self.pulseWidth = []
        self.digitalOutputs = []  # TODO: this never gets filled

    def _updateForABFv1(self):
        """
        Do our best to create an epoch from what we know about the ABFv1.
        Currently this makes it look like a single step epoch over the 
        entire sweep.
        """
        # TODO: support this better
        warnings.warn("ABFv1 epoch synthesis not fully supported")
        self.pointStart.append(0)
        self.pointEnd.append(self.abf.sweepPointCount)
        self.type.append(1)
        self.level.append(self.abf.holdingCommand[self.channel])
        self.levelDelta.append(0)
        self.duration.append(self.abf.sweepPointCount)
        self.durationDelta.append(0)
        self.pulsePeriod.append(0)
        self.pulseWidth.append(0)
        self.digitalOutputs.append(self.abf.sweepPointCount)

    def _addPreEpoch(self):
        """
        The pre-epoch period is 1/64th of the swep length (dear god why?!)
        so make a fake epoch to represent this pre-epoch
        """
        self._pointOffset = int(self.abf.sweepPointCount/64)

        self.pointStart.append(0)
        self.pointEnd.append(self._pointOffset)
        self.type.append(1)
        self.level.append(self.abf.holdingCommand[self.channel])
        self.levelDelta.append(0)
        self.duration.append(self._pointOffset)
        self.durationDelta.append(0)
        self.pulsePeriod.append(0)
        self.pulseWidth.append(0)
        self.digitalOutputs.append(self._pointOffset)

    def _fillEpochsFromABF(self):
        """
        Read the ABF header and append to the epoch lists
        """

        # load epoch values relevant to this channel
        for i, dacNum in enumerate(self.abf._epochPerDacSection.nDACNum):
            if dacNum != self.channel:
                continue
            epPerDac = self.abf._epochPerDacSection
            self.pointStart.append(self.pointStart[-1]+self.duration[-1])
            self.type.append(epPerDac.nEpochType[i])
            self.level.append(epPerDac.fEpochInitLevel[i])
            self.levelDelta.append(epPerDac.fEpochLevelInc[i])
            self.duration.append(epPerDac.lEpochInitDuration[i])
            self.durationDelta.append(epPerDac.lEpochDurationInc[i])
            self.pulsePeriod.append(epPerDac.lEpochPulsePeriod[i])
            self.pulseWidth.append(epPerDac.lEpochPulseWidth[i])
            self.pointEnd.append(self.pointStart[-1]+self.duration[-1])

    def _addPostEpoch(self):
        """
        There is ABF data after the last epoch is over. Create a fake epoch
        to represent this.
        """
        if self.abf._dacSection.nInterEpisodeLevel[self.channel]:
            # don't revert back to holding, sustain last epoch.
            # do this by extending the last epoch to the end of the sweep.
            self.pointEnd[-1] = self.abf.sweepPointCount-1 + self._pointOffset
        else:
            # revert back to holding
            self.pointStart.append(self.pointEnd[-1])  # TODO: +1?
            self.pointEnd.append(self.abf.sweepPointCount + self._pointOffset)
            self.type.append(1)
            self.level.append(self.level[-1])
            self.levelDelta.append(0)
            self.duration.append(0)
            self.durationDelta.append(0)
            self.pulsePeriod.append(0)
            self.pulseWidth.append(0)

    def _createEpochLabels(self):
        self.label = [chr(x+64) for x in range(len(self.type))]
        self.label[0] = "pre"
        if self.duration[-1] == 0:
            self.label[-1] = "post"

    def _prePulseDetermine(self):
        """
        What happens after the last epoch? Is it holding, or sustained?
        """
        if self.abf._dacSection.nInterEpisodeLevel[self.channel]:
            # if not, sustain the last epoch through to the end of the sweep
            self.pointEnd[-1] = self.abf.sweepPointCount-1 + self._pointOffset
        else:
            # if so, add a fake epoch (step) back to the holding values
            self.pointStart.append(self.pointEnd[-1])  # TODO: +1?
            self.pointEnd.append(self.abf.sweepPointCount + self._pointOffset)
            self.type.append(1)
            self.level.append(self.level[-1])
            self.levelDelta.append(0)
            self.duration.append(0)
            self.durationDelta.append(0)
            self.pulsePeriod.append(0)
            self.pulseWidth.append(0)

    def _updateEpochDetails(self):
        """
        After all epochs have been loaded, do some housekeeping
        """

        self.epochCount = len(self.type)
        self.epochList = range(self.epochCount)
        self.dacUnits = self.abf.dacUnits[self.channel]

    def _txtFmt(self, label, values):
        """
        Format a label and its values for text-block printing.
        """

        if label == "Type":
            for i, value in enumerate(values):
                if value == 0:
                    values[i] = "Off"
                elif value == 1:
                    values[i] = "Step"
                elif value == 2:
                    values[i] = "Ramp"
                else:
                    values[i] = "%d?" % value
                    msg = "UNSUPPORTED EPOCH TYPE: %d" % value
                    warnings.warn(msg)

        line = label.rjust(25, ' ')
        for val in values:
            if not isinstance(val, str):
                val = "%d" % val
            line += val.rjust(7, ' ')
        return line+"\n"

    @property
    def text(self):
        """
        Return all epoch levels as a text block, similar to how ClampFit does
        this when poking through the file properties dialog
        """
        out = "\n"
        out += self._txtFmt("Ch%d EPOCH" % self.channel, self.label)
        out += self._txtFmt("Type", self.type)
        out += self._txtFmt(f"First Level ({self.dacUnits})", self.level)
        out += self._txtFmt(f"Delta Level ({self.dacUnits})", self.levelDelta)
        out += self._txtFmt("First Duration (samples)", self.duration)
        out += self._txtFmt("Delta Duration (samples)", self.durationDelta)
        out += self._txtFmt("Train Period (samples)", self.pulsePeriod)
        out += self._txtFmt("Pulse Width (samples)", self.pulseWidth)
        out += self._txtFmt("Epoch Start (samples)", self.pointStart)
        out += self._txtFmt("Epoch End (samples)", self.pointEnd)
        out += "\n"
        return out

    def stimulusWaveform(self, sweepNumber=0):
        """
        Return a signal (the same size as a sweep) representing the command
        waveform of the DAC for the given channel. Since command waveforms
        can change sweep to sweep due to deltas, an optional sweep number can
        be given as an argument.
        """

        # start by creating the command signal filled with the holding command
        sweepC = np.full(self.abf.sweepPointCount,
                         self.abf.holdingCommand[self.channel])

        # then step through epoch by epoch filling it with its contents
        for epochNumber in self.epochList:

            # skip past disabled epochs
            if self.type[epochNumber]==0:
                continue

            # determine the sweep-dependent level
            sweepLevel = self.level[epochNumber]
            sweepLevel += self.levelDelta[epochNumber]*sweepNumber

            # simplify the bounds of the sweepC we intend to modify
            i1 = self.pointStart[epochNumber]
            i2 = self.pointEnd[epochNumber]

            # TODO: figure out if sweep length is real or short by 1/64
            if i2 > (len(sweepC)):
                i2 = len(sweepC)
                warnings.warn("sweep length is shorter than expected.")

            # create a numpy array to hold the waveform for only this epoch
            chunk = np.empty(int(i2-i1))

            # determine how to fill the chunk based on the epoch type
            if self.type[epochNumber]==1:
                # step epoch
                chunk.fill(sweepLevel)
            else:
                msg = f"unknown sweep type: {self.type[epochNumber]}"
                msg+= " (treating as a step)"
                chunk.fill(sweepLevel)

            # modify this chunk based on the type of waveform
            sweepC[i1:i2] = chunk

        return sweepC