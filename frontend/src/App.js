import React, { useState } from 'react';
import {
  Container,
  Paper,
  Typography,
  TextField,
  Button,
  Box,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Grid,
  Card,
  CardContent,
  InputAdornment,
  CircularProgress,
  Alert,
  Snackbar,
} from '@mui/material';
import axios from 'axios';
import { LoadingButton } from '@mui/lab';
import AddIcon from '@mui/icons-material/Add';
import ReactMarkdown from 'react-markdown';
import gfm from 'remark-gfm';

const MBTI_TYPES = [
  'UNKNOWN',
  'INTJ', 'INTP', 'ENTJ', 'ENTP',
  'INFJ', 'INFP', 'ENFJ', 'ENFP',
  'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ',
  'ISTP', 'ISFP', 'ESTP', 'ESFP'
];

const MONTHS = Array.from({ length: 12 }, (_, i) => ({
  value: i + 1,
  label: `${i + 1}月`
}));

const MIN_BUDGET = 50000;
const MAX_BUDGET = 500000;
const BUDGET_STEP = 10000;

function App() {
  const [members, setMembers] = useState([{
    age: 25,
    gender: 'male',
    mbti: 'UNKNOWN'
  }, {
    age: 28,
    gender: 'female',
    mbti: 'ENFP'
  }]);
  const [departureLocation, setDepartureLocation] = useState('東京');
  const [travelMonth, setTravelMonth] = useState(3);
  const [nights, setNights] = useState(1);
  const [budget, setBudget] = useState(100000);
  const [travelPlan, setTravelPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generatingStatus, setGeneratingStatus] = useState('');
  const [error, setError] = useState(null);
  const [snackbarOpen, setSnackbarOpen] = useState(false);

  const addMember = () => {
    setMembers([...members, { age: 25, gender: 'male', mbti: 'UNKNOWN' }]);
  };

  const updateMember = (index, field, value) => {
    const newMembers = [...members];
    newMembers[index] = { ...newMembers[index], [field]: value };
    setMembers(newMembers);
  };

  const removeMember = (indexToRemove) => {
    if (members.length > 1) {
      setMembers(members.filter((_, index) => index !== indexToRemove));
    } else {
      displayError('メンバーは最低1人必要です');
    }
  };

  const handleCloseSnackbar = () => {
    setSnackbarOpen(false);
  };

  const displayError = (errorMessage, errorDetails = null) => {
    let message = errorMessage;
    if (errorDetails) {
      if (errorDetails.validation_errors) {
        message = Object.entries(errorDetails.validation_errors)
          .map(([field, msg]) => `${field}: ${msg}`)
          .join('\n');
      } else if (errorDetails.error) {
        message = errorDetails.error;
      }
    }
    setError(message);
    setSnackbarOpen(true);
  };

  const handleSubmit = async () => {
    try {
      setLoading(true);
      setGeneratingStatus('旅行プランを生成中...');
      setError(null);
      
      const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
      const response = await axios.post(`${apiUrl}/api/travel-plan`, {
        members,
        departure_location: departureLocation,
        travel_month: parseInt(travelMonth),
        nights: parseInt(nights),
        budget: parseInt(budget)
      });
      
      setTravelPlan(response.data);
      setGeneratingStatus('');
      
    } catch (error) {
      console.error('Error:', error);
      setGeneratingStatus('');
      
      if (error.response) {
        const { data } = error.response;
        displayError(data.message, data.details);
      } else if (error.request) {
        displayError('サーバーに接続できません。インターネット接続を確認してください。');
      } else {
        displayError('予期せぬエラーが発生しました。');
      }
    } finally {
      setLoading(false);
    }
  };

  const validateForm = () => {
    if (!departureLocation.trim()) {
      displayError('出発地を入力してください');
      return false;
    }
    
    if (members.length === 0) {
      displayError('少なくとも1人のメンバーを指定してください');
      return false;
    }
    
    for (const member of members) {
      if (!member.age || member.age < 0 || member.age > 120) {
        displayError('年齢は0-120の範囲で指定してください');
        return false;
      }
    }
    
    return true;
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        旅行プランナー
      </Typography>

      <Paper elevation={3} sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          旅行メンバー情報
        </Typography>
        
        {members.map((member, index) => (
          <Box key={index} sx={{ mb: 3 }}>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={3}>
                <TextField
                  fullWidth
                  label="年齢"
                  type="number"
                  value={member.age}
                  onChange={(e) => updateMember(index, 'age', e.target.value)}
                  InputProps={{
                    inputProps: { min: 0, max: 120 }
                  }}
                />
              </Grid>
              <Grid item xs={3}>
                <FormControl fullWidth>
                  <InputLabel>性別</InputLabel>
                  <Select
                    value={member.gender}
                    label="性別"
                    onChange={(e) => updateMember(index, 'gender', e.target.value)}
                  >
                    <MenuItem value="male">男性</MenuItem>
                    <MenuItem value="female">女性</MenuItem>
                    <MenuItem value="other">その他</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={3}>
                <FormControl fullWidth>
                  <InputLabel>MBTI</InputLabel>
                  <Select
                    value={member.mbti}
                    label="MBTI"
                    onChange={(e) => updateMember(index, 'mbti', e.target.value)}
                  >
                    {MBTI_TYPES.map((type) => (
                      <MenuItem key={type} value={type}>
                        {type === 'UNKNOWN' ? '不明' : type}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={3}>
                <Button
                  variant="outlined"
                  color="error"
                  onClick={() => removeMember(index)}
                  disabled={members.length === 1}
                  fullWidth
                >
                  削除
                </Button>
              </Grid>
            </Grid>
          </Box>
        ))}

        <Button 
          variant="outlined" 
          onClick={addMember} 
          sx={{ mb: 3 }}
          startIcon={<AddIcon />}
        >
          メンバーを追加
        </Button>

        <Grid container spacing={2}>
          <Grid item xs={12}>
            <TextField
              fullWidth
              label="出発地"
              value={departureLocation}
              onChange={(e) => setDepartureLocation(e.target.value)}
              placeholder="例: 東京"
            />
          </Grid>
          <Grid item xs={4}>
            <FormControl fullWidth>
              <InputLabel>旅行月</InputLabel>
              <Select
                value={travelMonth}
                label="旅行月"
                onChange={(e) => setTravelMonth(e.target.value)}
              >
                {MONTHS.map((month) => (
                  <MenuItem key={month.value} value={month.value}>
                    {month.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={4}>
            <FormControl fullWidth>
              <InputLabel>宿泊数</InputLabel>
              <Select
                value={nights}
                label="宿泊数"
                onChange={(e) => setNights(e.target.value)}
              >
                <MenuItem value={0}>日帰り</MenuItem>
                <MenuItem value={1}>1泊2日</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={4}>
            <FormControl fullWidth>
              <InputLabel>予算（グループ全体）</InputLabel>
              <Select
                value={budget}
                label="予算（グループ全体）"
                onChange={(e) => setBudget(e.target.value)}
              >
                {Array.from(
                  { length: (MAX_BUDGET - MIN_BUDGET) / BUDGET_STEP + 1 },
                  (_, i) => MIN_BUDGET + i * BUDGET_STEP
                ).map((value) => (
                  <MenuItem key={value} value={value}>
                    ¥{value.toLocaleString()}
                  </MenuItem>
                ))}
              </Select>
              <Typography variant="caption" color="textSecondary" sx={{ mt: 1 }}>
                {members.length}人で合計¥{budget.toLocaleString()}（1人あたり約¥{Math.floor(budget / members.length).toLocaleString()}）
              </Typography>
            </FormControl>
          </Grid>
        </Grid>

        <LoadingButton
          loading={loading}
          variant="contained"
          color="primary"
          onClick={() => {
            if (validateForm()) {
              handleSubmit();
            }
          }}
          sx={{ mt: 3 }}
          fullWidth
        >
          {loading ? '生成中...' : 'プランを生成'}
        </LoadingButton>

        <Snackbar
          open={snackbarOpen}
          autoHideDuration={6000}
          onClose={handleCloseSnackbar}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        >
          <Alert
            onClose={handleCloseSnackbar}
            severity="error"
            variant="filled"
            sx={{ width: '100%' }}
          >
            {error}
          </Alert>
        </Snackbar>

        {generatingStatus && (
          <Box sx={{ mt: 2, textAlign: 'center' }}>
            <CircularProgress size={24} sx={{ mr: 1 }} />
            <Typography variant="body1" component="span" color="primary">
              {generatingStatus}
            </Typography>
          </Box>
        )}
      </Paper>

      {travelPlan && (
        <Paper elevation={3} sx={{ p: 3, mt: 3 }}>
          <Typography variant="h6" gutterBottom>
            旅行プラン
          </Typography>
          
          <Card>
            <CardContent>
              <Box
                className="markdown-body"
                sx={{
                  '& .markdown-body': {
                    backgroundColor: 'transparent',
                    fontFamily: 'inherit',
                  },
                  '& h1': {
                    fontSize: '2rem',
                    fontWeight: 'bold',
                    borderBottom: '2px solid #1976d2',
                    paddingBottom: '0.5rem',
                    marginTop: '2rem',
                    marginBottom: '1rem',
                    color: '#1976d2'
                  },
                  '& h2': {
                    fontSize: '1.5rem',
                    fontWeight: 'bold',
                    borderBottom: '1px solid #2196f3',
                    paddingBottom: '0.3rem',
                    marginTop: '1.5rem',
                    marginBottom: '1rem',
                    color: '#2196f3'
                  },
                  '& h3': {
                    fontSize: '1.2rem',
                    fontWeight: 'bold',
                    marginTop: '1.2rem',
                    marginBottom: '0.8rem',
                    color: '#1976d2'
                  },
                  '& ul, & ol': {
                    marginLeft: '1.5rem',
                    marginBottom: '1rem',
                    paddingLeft: '1rem'
                  },
                  '& li': {
                    marginBottom: '0.5rem'
                  },
                  '& p': {
                    marginBottom: '1rem',
                    lineHeight: '1.6'
                  },
                  '& hr': {
                    margin: '1rem 0',
                    border: 'none',
                    borderTop: '1px solid #e0e0e0'
                  }
                }}
              >
                <ReactMarkdown plugins={[gfm]} children={travelPlan.travel_plan} />
              </Box>
            </CardContent>
          </Card>
        </Paper>
      )}
    </Container>
  );
}

export default App; 